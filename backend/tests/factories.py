"""Фабрики вымышленных данных для тестов с БД."""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from itertools import count

from sqlalchemy.ext.asyncio import AsyncSession

from teamtime.db.models import BotChat, Employee, TelegramIdentity, TopicBinding, TopicKind
from teamtime.services.ingest import IncomingMessage
from tests.conftest import NOW, TEAM_CHAT

CHAT = TEAM_CHAT
SCHEDULE_THREAD = 11
DAILY_THREAD = 22
_ids = count(1000)


async def employee(
    session: AsyncSession,
    short_name: str = "Иванов И.И.",
    full_name: str | None = None,
    *,
    norm_hours: int = 160,
    rate: int = 500,
    tg_id: int | None = None,
) -> Employee:
    from teamtime.services.manual import short_name_key

    e = Employee(
        full_name=full_name or short_name.replace(" ", " Вымышленный ", 1),
        short_name=short_name,
        match_key=short_name_key(short_name),
        position="Разработчик",
        monthly_norm_minutes=norm_hours * 60,
        hourly_rate=Decimal(rate),
    )
    session.add(e)
    await session.flush()
    if tg_id is not None:
        session.add(
            TelegramIdentity(
                telegram_user_id=tg_id, display_name=f"user{tg_id}", employee_id=e.id, linked_at=NOW
            )
        )
        await session.flush()
    return e


async def forum(session: AsyncSession) -> None:
    """Темы форума в чате команды (сам чат уже создан и разрешён фикстурой maker)."""
    if await session.get(BotChat, CHAT) is None:
        session.add(
            BotChat(chat_id=CHAT, title="Вымышленная команда", is_forum=True, approved=True)
        )
        await session.flush()
    session.add_all(
        [
            TopicBinding(
                chat_id=CHAT, thread_id=SCHEDULE_THREAD, kind=TopicKind.SCHEDULE, title="Расписание"
            ),
            TopicBinding(
                chat_id=CHAT, thread_id=DAILY_THREAD, kind=TopicKind.DAILY, title="Дейлики"
            ),
        ]
    )
    await session.flush()


def message(
    text: str,
    *,
    author: int = 501,
    thread: int | None = DAILY_THREAD,
    message_id: int | None = None,
    sent_at: datetime | None = None,
    name: str = "🦊 лис",
    edited: bool = False,
) -> IncomingMessage:
    return IncomingMessage(
        chat_id=CHAT,
        message_id=message_id if message_id is not None else next(_ids),
        thread_id=thread,
        text=text,
        sent_at=sent_at or NOW - timedelta(hours=1),
        author_id=author,
        author_name=name,
        edited_at=NOW if edited else None,
    )


def schedule_text(name: str = "Иванов И.И.", sprint: str = "26.10 - 31.10", **days: str) -> str:
    lines = [f"Спринт {sprint}", name, ""]
    lines += [
        f"{d}: {v}" for d, v in (days or {"Пн": "10:00 - 18:00", "Вт": "10:00 - 18:00"}).items()
    ]
    lines += ["", "- задача один", "- задача два", "", "#расписание"]
    return "\n".join(lines)


def daily_text(day: str = "23.10.2026", spans: str = "10:00 - 18:00", e: int | None = 80) -> str:
    lines = [day, spans]
    if e is not None:
        lines.append(f"Эффективность: {e}%")
    lines += ["", "- сделал что-то", "", "#дейли"]
    return "\n".join(lines)
