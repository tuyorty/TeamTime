"""Напоминания тем, кто не прислал дейлик к заданному часу (если включено в настройках)."""

from __future__ import annotations

import asyncio
import contextlib
from datetime import date

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from teamtime.core import clock
from teamtime.core.logging import get_logger
from teamtime.db.models import TelegramIdentity
from teamtime.services.facts import active_employees, load_cells
from teamtime.services.settings import load_settings

log = get_logger(__name__)
CHECK_SECONDS = 60


async def due_reminders(session: AsyncSession) -> tuple[date | None, list[int]]:
    """Чаты, которым пора напомнить: план сегодня есть, дейлика нет, час напоминания настал."""
    settings = await load_settings(session)
    if not settings.bot.reminders_enabled:
        return None, []
    now = clock.now().astimezone(settings.tz)
    if now.hour < settings.bot.reminder_hour:
        return None, []
    today = now.date()
    employees = await active_employees(session)
    cells = await load_cells(session, settings, today, today, [e.id for e in employees])
    waiting = [
        e.id
        for e in employees
        if cells[(e.id, today)].result.planned and not cells[(e.id, today)].daily
    ]
    if not waiting:
        return today, []
    chats = await session.scalars(
        select(TelegramIdentity.dm_chat_id).where(
            TelegramIdentity.employee_id.in_(waiting), TelegramIdentity.dm_chat_id.is_not(None)
        )
    )
    return today, [c for c in chats if c is not None]


async def reminder_loop(bot: Bot, maker: async_sessionmaker[AsyncSession]) -> None:
    sent: dict[date, set[int]] = {}
    while True:
        try:
            async with maker() as session:
                today, chats = await due_reminders(session)
            if today is not None:
                done = sent.setdefault(today, set())
                for chat_id in chats:
                    if chat_id in done:
                        continue
                    with contextlib.suppress(TelegramAPIError):
                        await bot.send_message(
                            chat_id,
                            "Напоминание: дейлик за сегодня ещё не пришёл. "
                            "Пришлите его в тему «дейлики».",
                        )
                    done.add(chat_id)
                for old in [d for d in sent if d != today]:
                    del sent[old]
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # цикл не должен падать из-за одной ошибки
            log.warning("bot.reminders_failed", error=str(exc))
        await asyncio.sleep(CHECK_SECONDS)
