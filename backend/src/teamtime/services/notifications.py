"""Личные настройки и одно явно запрошенное повторное напоминание."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from teamtime.core import clock
from teamtime.db.models import DailyReminder, Employee, NotificationPreference
from teamtime.services import audit, manual


def next_allowed(now: datetime, preference: NotificationPreference | None) -> datetime:
    if preference is None or preference.quiet_start is None or preference.quiet_end is None:
        return now
    start, end = preference.quiet_start, preference.quiet_end
    minute = now.hour * 60 + now.minute
    quiet = start <= minute < end if start < end else minute >= start or minute < end
    if not quiet:
        return now
    target = now.replace(hour=end // 60, minute=end % 60, second=0, microsecond=0)
    return target if target > now else target + timedelta(days=1)


async def save_preferences(
    session: AsyncSession, employee_id: int, values: dict[str, Any], actor: str
) -> NotificationPreference:
    employee = await session.get(Employee, employee_id)
    if employee is None or not employee.is_active:
        raise manual.EditError("Сотрудник не найден или неактивен")
    row = await session.get(NotificationPreference, employee_id)
    if row is None:
        row = NotificationPreference(employee_id=employee_id)
        session.add(row)
    before = {
        key: getattr(row, key) for key in ("enabled", "delay_minutes", "quiet_start", "quiet_end")
    }
    for key in before:
        if key in values:
            setattr(row, key, values[key])
    if (row.quiet_start is None) != (row.quiet_end is None) or (
        row.quiet_start is not None and row.quiet_start == row.quiet_end
    ):
        raise manual.EditError("Начало и конец тихого времени должны различаться")
    await session.flush()
    await audit.record(
        session,
        actor=actor,
        action="notifications.update",
        entity_type="notification_preference",
        entity_id=employee_id,
        employee_id=employee_id,
        before=before,
        after={key: getattr(row, key) for key in before},
    )
    return row


async def snooze(
    session: AsyncSession, employee_id: int, work_date: date, chat_id: int
) -> DailyReminder:
    row = await session.scalar(
        select(DailyReminder)
        .where(
            DailyReminder.employee_id == employee_id,
            DailyReminder.work_date == work_date,
            DailyReminder.chat_id == chat_id,
        )
        .with_for_update()
    )
    if row is None or row.sent_at is None:
        raise manual.EditError("Напоминание не найдено")
    if clock.now() - row.sent_at > timedelta(days=1):
        raise manual.EditError("Это напоминание устарело. Проверьте день через /check.")
    if row.snooze_used:
        raise manual.EditError("Для этого дня повтор уже запрошен")
    row.snooze_used = True
    row.snooze_until = clock.now() + timedelta(minutes=30)
    await session.flush()
    return row
