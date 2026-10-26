"""Группа-форум: разбор сообщений и правок, реакции, /bind. Никаких разборок в теме."""

from __future__ import annotations

import asyncio
import contextlib
from datetime import UTC, datetime

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.filters import Command, CommandObject
from aiogram.types import Message, ReactionTypeEmoji
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from teamtime.bot.feedback import group_feedback
from teamtime.core.config import Settings
from teamtime.core.logging import get_logger
from teamtime.db.models import BotChat, RawMessage, Source, TopicBinding, TopicKind
from teamtime.services import audit
from teamtime.services.ingest import IncomingMessage, IngestOutcome, ingest
from teamtime.services.settings import AppSettings

log = get_logger(__name__)
router = Router(name="group")
router.message.filter(F.chat.type.in_({"group", "supergroup"}))
router.edited_message.filter(F.chat.type.in_({"group", "supergroup"}))

BIND_KINDS = {
    "расписание": TopicKind.SCHEDULE,
    "schedule": TopicKind.SCHEDULE,
    "дейлики": TopicKind.DAILY,
    "дейли": TopicKind.DAILY,
    "daily": TopicKind.DAILY,
}
CLEANUP_SECONDS = 20


def incoming(message: Message, *, edited: bool = False) -> IncomingMessage:
    user = message.from_user
    return IncomingMessage(
        chat_id=message.chat.id,
        message_id=message.message_id,
        thread_id=message.message_thread_id if message.is_topic_message else None,
        text=message.text or message.caption or "",
        sent_at=message.date,
        edited_at=datetime.fromtimestamp(message.edit_date, UTC)
        if edited and message.edit_date
        else None,
        author_id=user.id if user and not user.is_bot else None,
        author_name=user.full_name
        if user
        else (message.sender_chat.title or "" if message.sender_chat else ""),
        author_username=user.username if user else None,
        source=Source.TELEGRAM,
        chat_title=message.chat.title or "",
        is_forum=bool(message.chat.is_forum),
    )


async def give_feedback(
    bot: Bot,
    message: Message,
    outcome: IngestOutcome,
    settings: AppSettings,
    session: AsyncSession,
    config: Settings,
) -> None:
    fb = group_feedback(outcome, settings, bot_username=config.bot_username)
    raw = await session.get(RawMessage, outcome.raw_message_id) if outcome.raw_message_id else None

    # Старое предупреждение больше не нужно, если правка всё исправила.
    if raw and raw.bot_reply_message_id and not outcome.needs_attention and outcome.changed:
        with contextlib.suppress(TelegramAPIError):
            await bot.delete_message(message.chat.id, raw.bot_reply_message_id)
        raw.bot_reply_message_id = None

    reply = fb.reply
    if fb.reaction:
        try:
            await bot.set_message_reaction(
                message.chat.id, message.message_id, reaction=[ReactionTypeEmoji(emoji=fb.reaction)]
            )
        except TelegramBadRequest as exc:
            # Реакции выключены в чате или эмодзи недоступно — короткий ответ вместо реакции.
            log.warning("bot.reaction_failed", error=str(exc))
            reply = reply or ("Принято" if not outcome.needs_attention else None)
    if reply and outcome.needs_attention and raw and raw.bot_reply_message_id:
        with contextlib.suppress(TelegramAPIError):
            await bot.edit_message_text(
                reply,
                chat_id=message.chat.id,
                message_id=raw.bot_reply_message_id,
                disable_web_page_preview=True,
            )
        return
    if reply:
        sent = await message.reply(reply, disable_web_page_preview=True)
        if raw and outcome.needs_attention:
            raw.bot_reply_message_id = sent.message_id


@router.message(Command("bind", "unbind"))
async def bind(message: Message, command: CommandObject, bot: Bot, session: AsyncSession) -> None:
    user = message.from_user
    if user is None:
        return
    member = await bot.get_chat_member(message.chat.id, user.id)
    if member.status not in {"creator", "administrator"}:
        await _short_reply(message, "Привязывать темы могут только админы чата.")
        return
    thread_id = message.message_thread_id if message.is_topic_message else None
    if await session.get(BotChat, message.chat.id) is None:
        session.add(
            BotChat(
                chat_id=message.chat.id,
                title=message.chat.title or "",
                is_forum=bool(message.chat.is_forum),
            )
        )
        await session.flush()
    existing = await session.scalar(
        select(TopicBinding).where(
            TopicBinding.chat_id == message.chat.id,
            TopicBinding.thread_id.is_(None)
            if thread_id is None
            else TopicBinding.thread_id == thread_id,
        )
    )
    actor = f"bot:{user.id}"
    if command.command == "unbind":
        if existing:
            await audit.record(
                session,
                actor=actor,
                action="topic.unbind",
                entity_type="topic_binding",
                entity_id=existing.id,
                before={"kind": existing.kind.value},
            )
            await session.delete(existing)
        await _short_reply(message, "Тема отвязана.")
        return
    kind = BIND_KINDS.get((command.args or "").strip().lower())
    if kind is None:
        await _short_reply(message, "Использование: /bind расписание или /bind дейлики")
        return
    if existing:
        existing.kind = kind
    else:
        existing = TopicBinding(
            chat_id=message.chat.id, thread_id=thread_id, kind=kind, title=_topic_title(message)
        )
        session.add(existing)
    await session.flush()
    await audit.record(
        session,
        actor=actor,
        action="topic.bind",
        entity_type="topic_binding",
        entity_id=existing.id,
        after={"kind": kind.value, "thread_id": thread_id},
    )
    label = "расписаний" if kind is TopicKind.SCHEDULE else "дейликов"
    chat = await session.get(BotChat, message.chat.id)
    if chat is None or not chat.approved:
        await _short_reply(
            message,
            f"Тема для {label} записана, но чат ещё не разрешён. Админ разрешит его на сайте: "
            "«Админка → Telegram». До этого бот не принимает сообщения из чата.",
        )
        return
    await _short_reply(message, f"Готово: эта тема — для {label}.")


def _topic_title(message: Message) -> str:
    reply = message.reply_to_message
    if reply and reply.forum_topic_created:
        return reply.forum_topic_created.name
    return ""


async def _short_reply(message: Message, text: str) -> None:
    """Служебный ответ, который сам исчезает вместе с командой."""
    sent = await message.reply(text)

    async def cleanup() -> None:
        await asyncio.sleep(CLEANUP_SECONDS)
        for msg in (sent, message):
            with contextlib.suppress(TelegramAPIError):
                await msg.delete()

    asyncio.get_running_loop().create_task(cleanup())


@router.message(F.text | F.caption, ~F.text.startswith("/"))
async def on_message(
    message: Message, bot: Bot, session: AsyncSession, settings: AppSettings, config: Settings
) -> None:
    outcome = await ingest(session, incoming(message), settings)
    await session.commit()  # данные сохранены, даже если Telegram не ответит
    await give_feedback(bot, message, outcome, settings, session, config)


@router.edited_message(F.text | F.caption)
async def on_edit(
    message: Message, bot: Bot, session: AsyncSession, settings: AppSettings, config: Settings
) -> None:
    outcome = await ingest(session, incoming(message, edited=True), settings)
    await session.commit()
    await give_feedback(bot, message, outcome, settings, session, config)
