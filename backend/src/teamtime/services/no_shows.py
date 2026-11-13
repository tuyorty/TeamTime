"""Подтверждение невыхода: отдельное решение админа, без подмены расписания или дейлика."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from teamtime.calc.no_show import confirmed_shift_end
from teamtime.core import clock
from teamtime.db.models import DayNoShow, Employee
from teamtime.services import audit, events
from teamtime.services.settings import AppSettings


class NoShowError(ValueError):
    def __init__(self, message: str, status: int = 409) -> None:
        super().__init__(message)
        self.status = status


async def _employee_lock(session: AsyncSession, employee_id: int) -> None:
    employee = await session.scalar(
        select(Employee.id).where(Employee.id == employee_id).with_for_update()
    )
    if employee is None:
        raise NoShowError("Сотрудник не найден", 404)


def _reason(reason: str) -> str:
    reason = reason.strip()
    if not 3 <= len(reason) <= 1000:
        raise NoShowError("Укажите причину длиной от 3 до 1000 символов", 422)
    return reason


async def active(session: AsyncSession, employee_id: int, day: date) -> DayNoShow | None:
    return await session.scalar(
        select(DayNoShow)
        .where(
            DayNoShow.employee_id == employee_id,
            DayNoShow.date == day,
            DayNoShow.retracted_at.is_(None),
        )
        .execution_options(populate_existing=True)
    )


async def confirm(
    session: AsyncSession,
    settings: AppSettings,
    *,
    employee_id: int,
    day: date,
    expected_plan_id: int,
    expected_seconds: int,
    reason: str,
    actor: str,
) -> DayNoShow:
    """Сохранить проверенный снимок смены; повтор того же подтверждения не удваивает время."""
    from teamtime.services.facts import load_cells
    from teamtime.services.history import calculation_versions, settings_on

    reason = _reason(reason)
    await _employee_lock(session, employee_id)
    cell = (await load_cells(session, settings, day, day, [employee_id]))[employee_id, day]
    versions = await calculation_versions(session, day)
    if day in settings_on(settings, versions, day).holidays:
        raise NoShowError(
            "За праздничный день опоздание не начисляется: подтвердить невыход нельзя"
        )
    if cell.daily is not None:
        raise NoShowError("За день уже есть дейлик. Проверьте фактические часы вместо невыхода")
    if cell.result.status is not None and cell.result.status.cancels_plan:
        raise NoShowError("У дня есть согласованный статус, отменяющий план. Сначала проверьте его")
    existing = await active(session, employee_id, day)
    if existing is not None:
        if existing.plan_id == expected_plan_id and existing.seconds == expected_seconds:
            return existing
        raise NoShowError("Невыход уже подтверждён по другому плану. Обновите данные")
    plan = cell.result.plan
    if cell.plan is None or plan is None or not plan.has_time:
        raise NoShowError("Для подтверждения невыхода нужен действующий план с интервалами работы")
    if cell.plan.id != expected_plan_id or plan.planned_seconds != expected_seconds:
        raise NoShowError("План изменился после просмотра. Обновите день и проверьте часы")
    shift_end = confirmed_shift_end(plan)
    if shift_end is None:
        raise NoShowError(
            "Интервалы расписания пересекаются или записаны в неоднозначном порядке. "
            "Сначала исправьте план дня, затем подтвердите невыход"
        )
    ends_at = datetime.combine(day, time(), settings.tz) + timedelta(seconds=shift_end)
    if clock.now().astimezone(settings.tz) < ends_at:
        raise NoShowError("Смена ещё не закончилась. Подтвердить невыход можно после её окончания")
    row = DayNoShow(
        employee_id=employee_id,
        date=day,
        plan_id=expected_plan_id,
        seconds=expected_seconds,
        intervals=[[i.start, i.end] for i in plan.intervals],
        reason=reason,
        created_by=actor,
    )
    session.add(row)
    await session.flush()
    await audit.record(
        session,
        actor=actor,
        action="no_show.confirmed",
        entity_type="day_no_show",
        entity_id=row.id,
        employee_id=employee_id,
        after={"date": day.isoformat(), "plan_id": row.plan_id, "seconds": row.seconds},
        reason=reason,
    )
    await events.notify(
        session,
        "status.changed",
        employee_id=employee_id,
        dates=[day.isoformat()],
        kind="no_show",
        actor=actor,
    )
    return row


async def cancel(
    session: AsyncSession,
    *,
    employee_id: int,
    day: date,
    expected_id: int,
    reason: str,
    actor: str,
) -> DayNoShow:
    """Отменить конкретное решение, сохранив его и причину отмены в истории."""
    reason = _reason(reason)
    await _employee_lock(session, employee_id)
    row = await session.get(DayNoShow, expected_id, populate_existing=True)
    if row is None or row.employee_id != employee_id or row.date != day:
        raise NoShowError("Подтверждение невыхода не найдено", 404)
    current = await active(session, employee_id, day)
    if current is not None and current.id != expected_id:
        raise NoShowError("Подтверждение уже изменилось. Обновите данные")
    if row.retracted_at is not None:
        return row
    row.retracted_at = clock.now()
    await audit.record(
        session,
        actor=actor,
        action="no_show.cancelled",
        entity_type="day_no_show",
        entity_id=row.id,
        employee_id=employee_id,
        before={"date": day.isoformat(), "plan_id": row.plan_id, "seconds": row.seconds},
        after={"retracted": True},
        reason=reason,
    )
    await events.notify(
        session,
        "status.changed",
        employee_id=employee_id,
        dates=[day.isoformat()],
        kind="no_show",
        actor=actor,
    )
    return row
