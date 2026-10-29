"""Личное напоминание после смены: сохраняем попытку до отправки, чтобы не было дублей."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from aiogram import Bot
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramAPIError, TelegramForbiddenError, TelegramRetryAfter
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from teamtime.core import clock
from teamtime.core.config import Settings
from teamtime.core.logging import get_logger
from teamtime.db.models import (
    BotChat,
    DailyReminder,
    Employee,
    RawMessage,
    RawMessageVersion,
    TelegramIdentity,
    TopicBinding,
    TopicKind,
)
from teamtime.services.facts import DayCell, active_employees, load_cells
from teamtime.services.settings import AppSettings, load_settings

from .keyboards import reminder_menu
from .texts import format_reminder

log = get_logger(__name__)
CHECK_SECONDS = 60
MAX_ATTEMPTS = 3
CATCHUP_WINDOW = timedelta(hours=1)


@dataclass(frozen=True, slots=True)
class Reminder:
    employee_id: int
    name: str
    work_date: date
    chat_id: int
    shift_end: datetime
    delay_minutes: int
    topic_url: str | None = None


def _deadline(cell: DayCell, settings: AppSettings) -> datetime | None:
    """Ожидаем последний рабочий интервал, учитывая переход смены через полночь."""
    plan = cell.result.plan
    if cell.daily or not cell.result.planned or not plan or plan.end_abs is None:
        return None
    midnight = datetime.combine(cell.day, time.min, settings.tz)
    return midnight + timedelta(seconds=plan.end_abs, minutes=settings.bot.reminder_delay_minutes)


def _is_due(deadline: datetime | None, now: datetime) -> bool:
    # Короткий простой переживаем; старые напоминания после долгого отключения не рассылаем.
    return deadline is not None and deadline <= now < deadline + CATCHUP_WINDOW


async def due_reminders(session: AsyncSession) -> list[Reminder]:
    settings = await load_settings(session)
    if not settings.bot.reminders_enabled:
        return []
    now = clock.now().astimezone(settings.tz)
    start, end = now.date() - timedelta(days=2), now.date()
    employees = await active_employees(session)
    by_id = {employee.id: employee for employee in employees}
    cells = await load_cells(session, settings, start, end, by_id)
    due = {key: cell for key, cell in cells.items() if _is_due(_deadline(cell, settings), now)}
    if not due:
        return []
    identities = list(
        await session.scalars(
            select(TelegramIdentity).where(
                TelegramIdentity.employee_id.in_({key[0] for key in due}),
                TelegramIdentity.dm_chat_id.is_not(None),
            )
        )
    )
    existing = list(
        await session.scalars(
            select(DailyReminder).where(
                DailyReminder.work_date.between(start, end),
                DailyReminder.employee_id.in_(by_id),
            )
        )
    )
    unavailable = {
        (row.employee_id, row.work_date, row.chat_id)
        for row in existing
        if row.sent_at
        or row.attempted_at
        or row.attempts >= MAX_ATTEMPTS
        or (row.next_attempt_at and row.next_attempt_at > now)
    }
    topics = list(
        await session.scalars(
            select(TopicBinding)
            .join(BotChat)
            .where(
                BotChat.approved.is_(True),
                TopicBinding.kind == TopicKind.DAILY,
                TopicBinding.thread_id.is_not(None),
            )
        )
    )
    source_ids = {
        cell.plan.source_version_id
        for cell in due.values()
        if cell.plan and cell.plan.source_version_id
    }
    source_chats = dict(
        (
            await session.execute(
                select(RawMessageVersion.id, RawMessage.chat_id)
                .join(RawMessage, RawMessageVersion.raw_message_id == RawMessage.id)
                .where(RawMessageVersion.id.in_(source_ids))
            )
        ).all()
    )
    reminders = []
    seen: set[tuple[int, date, int]] = set()
    for (employee_id, day), cell in sorted(due.items(), key=lambda item: item[0][1]):
        deadline = _deadline(cell, settings)
        assert deadline is not None
        source_version = cell.plan.source_version_id if cell.plan else None
        source_chat = source_chats.get(source_version) if source_version is not None else None
        matching_topics = [topic for topic in topics if topic.chat_id == source_chat]
        topic = (
            matching_topics[0]
            if len(matching_topics) == 1
            else topics[0]
            if len(topics) == 1
            else None
        )
        topic_url = None
        if topic and str(topic.chat_id).startswith("-100"):
            topic_url = f"https://t.me/c/{str(topic.chat_id)[4:]}/{topic.thread_id}"
        for identity in identities:
            chat_id = identity.dm_chat_id
            if identity.employee_id != employee_id or chat_id is None:
                continue
            key = (employee_id, day, chat_id)
            if key in unavailable or key in seen:
                continue
            seen.add(key)
            reminders.append(
                Reminder(
                    employee_id=employee_id,
                    name=by_id[employee_id].short_name,
                    work_date=day,
                    chat_id=chat_id,
                    shift_end=deadline - timedelta(minutes=settings.bot.reminder_delay_minutes),
                    delay_minutes=settings.bot.reminder_delay_minutes,
                    topic_url=topic_url,
                )
            )
    return reminders


async def send_due_reminders(
    bot: Bot, maker: async_sessionmaker[AsyncSession], config: Settings
) -> int:
    """Повторяем только явный отказ Telegram (429); при неизвестном результате дубль опаснее."""
    async with maker() as session:
        candidates = await due_reminders(session)
    sent = 0
    for candidate in candidates:
        async with maker() as session:
            key = (candidate.employee_id, candidate.work_date, candidate.chat_id)
            await session.execute(
                insert(DailyReminder)
                .values(
                    employee_id=candidate.employee_id,
                    work_date=candidate.work_date,
                    chat_id=candidate.chat_id,
                )
                .on_conflict_do_nothing()
            )
            record = await session.scalar(
                select(DailyReminder)
                .where(
                    DailyReminder.employee_id == key[0],
                    DailyReminder.work_date == key[1],
                    DailyReminder.chat_id == key[2],
                )
                .with_for_update(skip_locked=True)
            )
            now = clock.now()
            if (
                record is None
                or record.sent_at
                or record.attempted_at
                or record.attempts >= MAX_ATTEMPTS
                or (record.next_attempt_at and record.next_attempt_at > now)
            ):
                continue
            settings = await load_settings(session)
            employee = await session.get(Employee, candidate.employee_id)
            identity = await session.scalar(
                select(TelegramIdentity)
                .where(
                    TelegramIdentity.employee_id == candidate.employee_id,
                    TelegramIdentity.dm_chat_id == candidate.chat_id,
                )
                .limit(1)
            )
            if (
                not settings.bot.reminders_enabled
                or not employee
                or not employee.is_active
                or not identity
            ):
                continue
            cells = await load_cells(
                session, settings, candidate.work_date, candidate.work_date, [candidate.employee_id]
            )
            deadline = _deadline(cells[(candidate.employee_id, candidate.work_date)], settings)
            if not _is_due(deadline, now):
                continue
            assert deadline is not None
            shift_end = deadline - timedelta(minutes=settings.bot.reminder_delay_minutes)
            # Отдельный коммит до сети закрывает окно «отправлено, но бот упал до сохранения».
            # При падении или потере ответа эта попытка останется неопределённой без автоповтора.
            record.attempted_at = now
            record.attempts += 1
            record.next_attempt_at = None
            await session.commit()
            try:
                await bot.send_message(
                    candidate.chat_id,
                    format_reminder(
                        employee.short_name,
                        candidate.work_date,
                        shift_end,
                        settings.bot.reminder_delay_minutes,
                    ),
                    parse_mode=ParseMode.HTML,
                    reply_markup=reminder_menu(
                        config.public_url, candidate.work_date, candidate.topic_url
                    ),
                )
            except TelegramForbiddenError:
                # Новое сообщение в личке снова включит доставку для этого аккаунта.
                identity.dm_chat_id = None
                record.attempted_at = None
                log.info("bot.reminder_unavailable", employee_id=candidate.employee_id)
            except TelegramRetryAfter as exc:
                # 429 однозначно означает, что сообщение не отправлено. Число попыток ограничено.
                if record.attempts < MAX_ATTEMPTS:
                    record.attempted_at = None
                    record.next_attempt_at = now + timedelta(
                        seconds=max(CHECK_SECONDS * 2 ** (record.attempts - 1), exc.retry_after)
                    )
                log.warning(
                    "bot.reminder_retry",
                    employee_id=candidate.employee_id,
                    retry_after=exc.retry_after,
                    attempts=record.attempts,
                )
            except TelegramAPIError as exc:
                log.warning(
                    "bot.reminder_delivery_unknown",
                    employee_id=candidate.employee_id,
                    error=type(exc).__name__,
                )
            else:
                record.sent_at = now
                record.next_attempt_at = None
                sent += 1
            await session.commit()
    return sent


async def reminder_loop(
    bot: Bot, maker: async_sessionmaker[AsyncSession], config: Settings
) -> None:
    while True:
        try:
            await send_due_reminders(bot, maker, config)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # ошибка одного прохода не останавливает напоминания
            log.warning("bot.reminders_failed", error=type(exc).__name__)
        await asyncio.sleep(CHECK_SECONDS)
