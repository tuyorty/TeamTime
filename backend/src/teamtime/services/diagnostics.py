"""Наблюдаемость без токенов, адресов прокси и содержимого личных сообщений."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from teamtime import __version__
from teamtime.core import clock
from teamtime.db.models import (
    BotDelivery,
    DailyReminder,
    Employee,
    NotificationPreference,
    SystemStatus,
    TelegramIdentity,
)
from teamtime.services.settings import AppSettings


class ServiceOut(BaseModel):
    service: str
    state: str
    heartbeat_at: datetime | None = None
    last_success_at: datetime | None = None
    last_update_at: datetime | None = None
    last_error_at: datetime | None = None
    error_code: str | None = None
    details: dict[str, Any] = {}


class DeliveryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    kind: str
    employee_id: int | None
    raw_message_id: int | None
    state: str
    attempts: int
    created_at: datetime
    completed_at: datetime | None
    error_code: str | None


class DMOut(BaseModel):
    employee_id: int
    name: str
    ready: bool
    enabled: bool
    delay_minutes: int
    quiet_start: int | None
    quiet_end: int | None


class ReminderOut(BaseModel):
    employee_id: int
    work_date: str
    state: str
    attempts: int
    sent_at: datetime | None
    deferred_until: datetime | None
    snooze_until: datetime | None
    followup_sent_at: datetime | None
    error_code: str | None


class SystemOut(BaseModel):
    version: str
    checked_at: datetime
    database: str
    migration: str | None
    services: list[ServiceOut]
    deliveries: list[DeliveryOut]
    reminders: list[ReminderOut]
    personal_notifications: list[DMOut]


async def set_service(
    session: AsyncSession,
    service: str,
    state: str,
    *,
    success: bool = False,
    error_code: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    now = clock.now()
    values: dict[str, Any] = {
        "service": service,
        "state": state,
        "heartbeat_at": now,
        "details": details or {},
    }
    changed: dict[str, Any] = {"state": state, "heartbeat_at": now}
    if success:
        values["last_success_at"] = changed["last_success_at"] = now
    if error_code:
        values["last_error_at"] = changed["last_error_at"] = now
        values["error_code"] = changed["error_code"] = error_code[:100]
    if details is not None:
        changed["details"] = details
    statement = insert(SystemStatus).values(**values)
    await session.execute(
        statement.on_conflict_do_update(index_elements=[SystemStatus.service], set_=changed)
    )


async def touch_update(session: AsyncSession) -> None:
    from sqlalchemy import update

    await session.execute(
        update(SystemStatus).where(SystemStatus.service == "bot").values(last_update_at=clock.now())
    )


async def begin_delivery(
    session: AsyncSession,
    kind: str,
    *,
    employee_id: int | None = None,
    raw_message_id: int | None = None,
) -> BotDelivery:
    row = BotDelivery(
        kind=kind,
        employee_id=employee_id,
        raw_message_id=raw_message_id,
        state="attempted",
        attempts=0,
    )
    session.add(row)
    await session.commit()
    return row


async def finish_delivery(
    session: AsyncSession, row: BotDelivery, state: str, error_code: str | None = None
) -> None:
    row.state, row.completed_at, row.error_code = state, clock.now(), error_code
    await session.commit()


async def system_state(session: AsyncSession, settings: AppSettings) -> SystemOut:
    migration = await session.scalar(text("SELECT version_num FROM alembic_version LIMIT 1"))
    now = clock.now()
    services = {row.service: row for row in await session.scalars(select(SystemStatus))}
    output = []
    for name in ("bot", "backup"):
        row = services.get(name)
        if row is None:
            output.append(ServiceOut(service=name, state="unknown"))
            continue
        state = row.state
        if (
            name == "backup"
            and state == "ok"
            and row.last_success_at
            and (now - row.last_success_at).total_seconds() > 36 * 3600
        ):
            state = "stale"
        if (
            name == "bot"
            and state not in {"stopped", "unknown"}
            and (now - row.heartbeat_at).total_seconds() > 150
        ):
            state = "stale"
        output.append(
            ServiceOut(
                service=name,
                state=state,
                heartbeat_at=row.heartbeat_at,
                last_success_at=row.last_success_at,
                last_update_at=row.last_update_at,
                last_error_at=row.last_error_at,
                error_code=row.error_code,
                details=row.details,
            )
        )
    deliveries = await session.scalars(
        select(BotDelivery).order_by(BotDelivery.created_at.desc(), BotDelivery.id.desc()).limit(50)
    )
    reminders = await session.scalars(
        select(DailyReminder)
        .order_by(DailyReminder.work_date.desc(), DailyReminder.employee_id)
        .limit(50)
    )
    identities = list(
        await session.scalars(
            select(TelegramIdentity).where(TelegramIdentity.dm_chat_id.is_not(None))
        )
    )
    ready_ids = {row.employee_id for row in identities}
    preferences = {p.employee_id: p for p in await session.scalars(select(NotificationPreference))}
    employees = await session.scalars(
        select(Employee).where(Employee.is_active).order_by(Employee.short_name)
    )
    dm = []
    for employee in employees:
        preference = preferences.get(employee.id)
        dm.append(
            DMOut(
                employee_id=employee.id,
                name=employee.short_name,
                ready=employee.id in ready_ids,
                enabled=settings.bot.reminders_enabled
                and (preference.enabled if preference else True),
                delay_minutes=(preference.delay_minutes if preference else None)
                or settings.bot.reminder_delay_minutes,
                quiet_start=preference.quiet_start if preference else None,
                quiet_end=preference.quiet_end if preference else None,
            )
        )
    return SystemOut(
        version=__version__,
        checked_at=now,
        database="ok",
        migration=migration,
        services=output,
        deliveries=[DeliveryOut.model_validate(row) for row in deliveries],
        reminders=[
            ReminderOut(
                employee_id=row.employee_id,
                work_date=row.work_date.isoformat(),
                state="sent"
                if row.sent_at
                else "unknown"
                if row.attempted_at
                else "deferred"
                if row.deferred_until or row.next_attempt_at
                else "pending",
                attempts=row.attempts,
                sent_at=row.sent_at,
                deferred_until=row.deferred_until,
                snooze_until=row.snooze_until,
                followup_sent_at=row.followup_sent_at,
                error_code=row.error_code,
            )
            for row in reminders
        ],
        personal_notifications=dm,
    )
