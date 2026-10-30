"""Действовавшие в периоде условия. Будущая настройка не меняет текущие расчёты."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from teamtime.core import clock
from teamtime.db.models import CalculationVersion, Employee, EmployeeTerms

if TYPE_CHECKING:
    from teamtime.services.settings import AppSettings

BASE_DATE = date(2000, 1, 1)
CALC_FIELDS = frozenset(
    {
        "timezone",
        "late_tolerance_min",
        "early_tolerance_min",
        "undertime_tolerance_min",
        "plan_notice_hours",
        "weekly_off",
        "holidays",
        "penalty",
    }
)


def month_start(day: date) -> date:
    return day.replace(day=1)


def calculation_values(settings: AppSettings) -> dict[str, Any]:
    return settings.model_dump(mode="json", include=set(CALC_FIELDS))


async def calculation_versions(session: AsyncSession, end: date) -> list[CalculationVersion]:
    return list(
        await session.scalars(
            select(CalculationVersion)
            .where(CalculationVersion.effective_from <= end)
            .order_by(CalculationVersion.effective_from)
        )
    )


def settings_on(
    settings: AppSettings, versions: list[CalculationVersion], day: date
) -> AppSettings:
    from teamtime.services.settings import AppSettings

    chosen = next((v for v in reversed(versions) if v.effective_from <= day), None)
    if chosen is None:
        return settings
    payload = settings.model_dump(mode="json")
    payload.update({key: value for key, value in chosen.value.items() if key in CALC_FIELDS})
    return AppSettings.model_validate(payload)


async def settings_at(session: AsyncSession, settings: AppSettings, day: date) -> AppSettings:
    return settings_on(settings, await calculation_versions(session, day), day)


async def settings_current(
    session: AsyncSession, settings: AppSettings, now: datetime
) -> AppSettings:
    """Месяц наступает в прежнем поясе: будущий пояс не включает свою версию раньше срока."""
    versions = await calculation_versions(session, now.date() + timedelta(days=2))
    active = settings
    for version in versions:
        if version.effective_from > now.astimezone(active.tz).date():
            break
        active = settings_on(active, [version], version.effective_from)
    return active


async def record_settings(
    session: AsyncSession,
    previous: AppSettings,
    value: AppSettings,
    effective_from: date,
    actor: str,
) -> None:
    if effective_from.day != 1 or not BASE_DATE <= effective_from <= date(2100, 12, 1):
        raise ValueError("Для правил расчёта укажите первый день месяца в диапазоне 2000–2100")
    rows = await calculation_versions(session, date(2100, 12, 31))
    applicable = settings_on(previous, rows, effective_from)
    if calculation_values(applicable) == calculation_values(value):
        return
    if not rows:
        session.add(
            CalculationVersion(
                effective_from=BASE_DATE, value=calculation_values(previous), created_by=actor
            )
        )
        await session.flush()
    existing = await session.scalar(
        select(CalculationVersion).where(CalculationVersion.effective_from == effective_from)
    )
    if existing:
        existing.value = calculation_values(value)
        existing.created_by = actor
    else:
        session.add(
            CalculationVersion(
                effective_from=effective_from, value=calculation_values(value), created_by=actor
            )
        )


async def record_terms(
    session: AsyncSession,
    employee: Employee,
    before: dict[str, Any] | None,
    effective_from: date,
    actor: str,
) -> None:
    if effective_from.day != 1 or not BASE_DATE <= effective_from <= date(2100, 12, 1):
        raise ValueError("Для нормы и ставки укажите первый день месяца в диапазоне 2000–2100")
    rows = list(
        await session.scalars(select(EmployeeTerms).where(EmployeeTerms.employee_id == employee.id))
    )
    applicable = max(
        (row for row in rows if row.effective_from <= effective_from),
        key=lambda row: row.effective_from,
        default=None,
    )
    if applicable:
        if (
            applicable.monthly_norm_minutes == employee.monthly_norm_minutes
            and applicable.hourly_rate == employee.hourly_rate
        ):
            return
    elif before and (
        int(before["monthly_norm_minutes"]) == employee.monthly_norm_minutes
        and Decimal(str(before["hourly_rate"])) == employee.hourly_rate
    ):
        return
    if not rows:
        session.add(
            EmployeeTerms(
                employee_id=employee.id,
                effective_from=BASE_DATE,
                monthly_norm_minutes=int(before["monthly_norm_minutes"])
                if before
                else employee.monthly_norm_minutes,
                hourly_rate=Decimal(str(before["hourly_rate"])) if before else employee.hourly_rate,
                created_by=actor,
            )
        )
        await session.flush()
    existing = await session.scalar(
        select(EmployeeTerms).where(
            EmployeeTerms.employee_id == employee.id, EmployeeTerms.effective_from == effective_from
        )
    )
    if existing:
        existing.monthly_norm_minutes = employee.monthly_norm_minutes
        existing.hourly_rate = employee.hourly_rate
        existing.created_by = actor
    else:
        session.add(
            EmployeeTerms(
                employee_id=employee.id,
                effective_from=effective_from,
                monthly_norm_minutes=employee.monthly_norm_minutes,
                hourly_rate=employee.hourly_rate,
                created_by=actor,
            )
        )


async def terms_at(
    session: AsyncSession, employee_ids: list[int], day: date
) -> dict[int, EmployeeTerms]:
    rows = await session.scalars(
        select(EmployeeTerms)
        .where(EmployeeTerms.employee_id.in_(employee_ids), EmployeeTerms.effective_from <= day)
        .order_by(EmployeeTerms.effective_from, EmployeeTerms.id)
    )
    return {row.employee_id: row for row in rows}


def default_effective_month(settings: AppSettings) -> date:
    return clock.now().astimezone(settings.tz).date().replace(day=1)
