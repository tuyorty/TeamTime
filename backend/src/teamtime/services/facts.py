"""Сборка дней из базы: актуальные версии планов и дейликов, статусы, настройки → DayResult.

Расчёты не хранятся (см. architecture.md), их собирают здесь на лету. Каждая ячейка
помнит, из каких версий она получена: так сайт показывает «источник» любой цифры.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from teamtime.calc import DayResult, FactInput, PlanInput, compute_day
from teamtime.core import clock
from teamtime.db.models import Daily, DayStatus, Employee, PlanDay, SchedulePlan
from teamtime.parsing import Interval
from teamtime.services.settings import AppSettings


@dataclass(slots=True)
class DayCell:
    employee_id: int
    day: date
    result: DayResult
    plan: SchedulePlan | None
    plan_day: PlanDay | None
    daily: Daily | None
    status: DayStatus | None


def date_range(start: date, end: date) -> Iterator[date]:
    """Дни от ``start`` до ``end`` включительно."""
    for n in range((end - start).days + 1):
        yield start + timedelta(days=n)


def today_local(settings: AppSettings) -> date:
    return clock.now().astimezone(settings.tz).date()


async def current_plans(
    session: AsyncSession, start: date, end: date, employee_ids: Iterable[int] | None = None
) -> list[SchedulePlan]:
    """Актуальная версия плана на каждую неделю, которая пересекается с диапазоном."""
    q = (
        select(SchedulePlan)
        .where(
            SchedulePlan.retracted_at.is_(None),
            SchedulePlan.week_start <= end,
            SchedulePlan.week_start >= start - timedelta(days=6),
        )
        .ext(distinct_on(SchedulePlan.employee_id, SchedulePlan.iso_year, SchedulePlan.iso_week))
        .order_by(
            SchedulePlan.employee_id,
            SchedulePlan.iso_year,
            SchedulePlan.iso_week,
            SchedulePlan.version.desc(),
        )
        .options(
            selectinload(SchedulePlan.days),
            selectinload(SchedulePlan.tasks),
            selectinload(SchedulePlan.source_version),
        )
    )
    if employee_ids is not None:
        q = q.where(SchedulePlan.employee_id.in_(list(employee_ids)))
    return list(await session.scalars(q))


async def current_dailies(
    session: AsyncSession, start: date, end: date, employee_ids: Iterable[int] | None = None
) -> list[Daily]:
    q = (
        select(Daily)
        .where(Daily.retracted_at.is_(None), Daily.work_date.between(start, end))
        .ext(distinct_on(Daily.employee_id, Daily.work_date))
        .order_by(Daily.employee_id, Daily.work_date, Daily.version.desc())
        .options(
            selectinload(Daily.intervals),
            selectinload(Daily.tasks),
            selectinload(Daily.source_version),
        )
    )
    if employee_ids is not None:
        q = q.where(Daily.employee_id.in_(list(employee_ids)))
    return list(await session.scalars(q))


async def current_statuses(
    session: AsyncSession, start: date, end: date, employee_ids: Iterable[int] | None = None
) -> list[DayStatus]:
    q = select(DayStatus).where(
        DayStatus.retracted_at.is_(None), DayStatus.date.between(start, end)
    )
    if employee_ids is not None:
        q = q.where(DayStatus.employee_id.in_(list(employee_ids)))
    return list(await session.scalars(q))


def plan_input(day: PlanDay) -> PlanInput:
    return PlanInput(
        kind=day.kind,
        intervals=tuple(Interval(a, b) for a, b in day.intervals),
        note=day.note,
    )


def fact_input(daily: Daily) -> FactInput:
    return FactInput(
        intervals=tuple(Interval(i.start_sec, i.end_sec) for i in daily.intervals),
        efficiency=daily.efficiency,
    )


async def active_employees(
    session: AsyncSession, *, include_inactive: bool = False
) -> list[Employee]:
    q = select(Employee).order_by(Employee.short_name)
    if not include_inactive:
        q = q.where(Employee.is_active)
    return list(await session.scalars(q))


async def load_cells(
    session: AsyncSession,
    settings: AppSettings,
    start: date,
    end: date,
    employee_ids: Iterable[int],
    *,
    today: date | None = None,
) -> dict[tuple[int, date], DayCell]:
    """Все ячейки «сотрудник × день» за диапазон, включая пустые."""
    ids = list(employee_ids)
    today = today or today_local(settings)
    rules = settings.day_rules()

    plan_days: dict[tuple[int, date], tuple[SchedulePlan, PlanDay]] = {}
    plans = await current_plans(session, start, end, ids)
    for p in plans:
        for d in p.days:
            # Если недели двух планов пересекаются датами (длинный спринт), берём более свежий.
            key = (p.employee_id, d.date)
            if key not in plan_days or plan_days[key][0].created_at < p.created_at:
                plan_days[key] = (p, d)
    plans_by_week = {(p.employee_id, p.week_start): p for p in plans}
    dailies = {
        (d.employee_id, d.work_date): d for d in await current_dailies(session, start, end, ids)
    }
    statuses = {
        (s.employee_id, s.date): s for s in await current_statuses(session, start, end, ids)
    }

    cells: dict[tuple[int, date], DayCell] = {}
    for emp in ids:
        for day in date_range(start, end):
            key = (emp, day)
            plan: SchedulePlan | None
            pday: PlanDay | None
            plan, pday = plan_days.get(key, (None, None))
            if plan is None:
                plan = plans_by_week.get((emp, day - timedelta(days=day.weekday())))
            daily = dailies.get(key)
            status = statuses.get(key)
            result = compute_day(
                day,
                plan_input(pday) if pday else None,
                fact_input(daily) if daily else None,
                status.kind if status else None,
                rules,
                today,
            )
            cells[key] = DayCell(emp, day, result, plan, pday, daily, status)
    return cells
