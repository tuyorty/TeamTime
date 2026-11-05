"""Напоминание за час до первой смены: только в личку, без повторов после сбоев."""

from datetime import datetime, time, timedelta
from html import escape

from aiogram import Bot
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramAPIError, TelegramForbiddenError, TelegramRetryAfter
from aiohttp_socks import ProxyConnectionError, ProxyError, ProxyTimeoutError
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from teamtime.calc import StatusKind
from teamtime.core import clock
from teamtime.core.logging import get_logger
from teamtime.db.models import Employee, NotificationPreference, ShiftReminder, TelegramIdentity
from teamtime.services.facts import DayCell, active_employees, load_cells
from teamtime.services.notifications import next_allowed
from teamtime.services.settings import AppSettings, load_settings

log = get_logger(__name__)
LEAD = timedelta(hours=1)
CATCHUP = timedelta(minutes=10)
MAX_ATTEMPTS = 3


def shift_start(cell: DayCell, settings: AppSettings) -> datetime | None:
    """Отсутствия и дни без точного плана не порождают напоминания."""
    plan = cell.result.plan
    if cell.daily or not cell.result.planned or not plan or plan.start is None:
        return None
    return datetime.combine(cell.day, time.min, settings.tz) + timedelta(seconds=plan.start)


def is_due(start: datetime, now: datetime, preference: NotificationPreference | None) -> bool:
    due = next_allowed(start - LEAD, preference)
    return due <= now < min(due + CATCHUP, start) and next_allowed(now, preference) <= now


def reminder_text(name: str, start: datetime, remote: bool) -> str:
    location = (
        "Удалённо — подключайтесь к работе вовремя." if remote else "В офисе — пора собираться."
    )
    return (
        "🕘 <b>Скоро рабочий день</b>\n\n"
        f"{escape(name)}, по расписанию начало <b>{start:%d.%m в %H:%M}</b>.\n"
        f"{location}\n\n"
        "Если планы изменились, обновите расписание или отправьте заявку через /absent."
    )


async def send_shift_reminders(bot: Bot, maker: async_sessionmaker[AsyncSession]) -> int:
    async with maker() as session:
        settings = await load_settings(session)
        if not settings.bot.reminders_enabled:
            return 0
        now = clock.now().astimezone(settings.tz)
        employees = await active_employees(session)
        cells = await load_cells(
            session, settings, now.date(), now.date() + timedelta(days=1), [e.id for e in employees]
        )
        preferences = {
            p.employee_id: p for p in await session.scalars(select(NotificationPreference))
        }
        candidates = []
        for key, cell in cells.items():
            preference = preferences.get(key[0])
            if preference and (not preference.enabled or not preference.arrival_enabled):
                continue
            start = shift_start(cell, settings)
            if start is not None and is_due(start, now, preference):
                candidates.append(key)

    sent = 0
    for employee_id, day in candidates:
        async with maker() as session:
            # Повторная проверка непосредственно перед отправкой учитывает правку/отмену плана.
            settings = await load_settings(session)
            now = clock.now().astimezone(settings.tz)
            preference = await session.get(NotificationPreference, employee_id)
            employee = await session.get(Employee, employee_id)
            if (
                not settings.bot.reminders_enabled
                or not employee
                or not employee.is_active
                or (preference and (not preference.enabled or not preference.arrival_enabled))
            ):
                continue
            identity = await session.scalar(
                select(TelegramIdentity)
                .where(
                    TelegramIdentity.employee_id == employee_id,
                    TelegramIdentity.removed_at.is_(None),
                    TelegramIdentity.dm_chat_id > 0,
                )
                .order_by(TelegramIdentity.last_seen_at.desc(), TelegramIdentity.id.desc())
                .limit(1)
            )
            if identity is None or identity.dm_chat_id is None:
                continue
            current = await load_cells(session, settings, day, day, [employee_id])
            cell = current[(employee_id, day)]
            start = shift_start(cell, settings)
            if start is None or not is_due(start, now, preference):
                continue
            await session.execute(
                insert(ShiftReminder)
                .values(
                    employee_id=employee_id,
                    work_date=day,
                    chat_id=identity.dm_chat_id,
                    shift_start=start,
                )
                .on_conflict_do_nothing()
            )
            record = await session.scalar(
                select(ShiftReminder)
                .where(
                    ShiftReminder.employee_id == employee_id,
                    ShiftReminder.work_date == day,
                )
                .with_for_update(skip_locked=True)
            )
            if (
                record is None
                or record.attempted_at is not None
                or record.sent_at is not None
                or record.attempts >= MAX_ATTEMPTS
                or (record.next_attempt_at is not None and record.next_attempt_at > now)
            ):
                continue
            record.chat_id, record.shift_start = identity.dm_chat_id, start
            record.attempted_at = now
            record.attempts += 1
            record.next_attempt_at = None
            text = reminder_text(
                employee.short_name, start, cell.result.status is StatusKind.REMOTE
            )
            # Фиксация до сети: при падении между отправкой и сохранением дубль не появится.
            await session.commit()
            try:
                await bot.send_message(
                    record.chat_id, text, parse_mode=ParseMode.HTML, request_timeout=15
                )
            except TelegramForbiddenError:
                identity.dm_chat_id = None
                record.error_code = "TelegramForbiddenError"
            except TelegramRetryAfter as exc:
                record.error_code = "TelegramRetryAfter"
                if record.attempts < MAX_ATTEMPTS:
                    record.attempted_at = None
                    record.next_attempt_at = now + timedelta(
                        seconds=max(60 * 2 ** (record.attempts - 1), exc.retry_after)
                    )
            except (TelegramAPIError, ProxyConnectionError, ProxyError, ProxyTimeoutError) as exc:
                record.error_code = type(exc).__name__
            else:
                record.sent_at = now
                record.error_code = None
                sent += 1
            if record.error_code:
                log.warning(
                    "bot.shift_reminder_failed",
                    employee_id=employee_id,
                    error=record.error_code,
                    attempts=record.attempts,
                )
            await session.commit()
    return sent
