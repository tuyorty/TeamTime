"""Сборка дней из базы: актуальные версии планов и дейликов, статусы, настройки → DayResult.

Расчёты не хранятся (см. architecture.md), их собирают здесь на лету. Каждая ячейка
помнит, из каких версий она получена: так сайт показывает «источник» любой цифры.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import distinct_on
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from teamtime.calc import DayResult, FactInput, PlanInput, compute_day
from teamtime.core import clock
from teamtime.db.models import (
    Daily,
    DayStatus,
    Employee,
    ParseResultRow,
    PlanDay,
    RawMessage,
    RawMessageVersion,
    Resolution,
    SchedulePlan,
    Source,
)
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
    late_edit: SchedulePlan | None = None
    """Свежая версия плана, которая пришла после начала дня и для этого дня не учтена."""


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


Stated = dict[int, datetime]
"""id версии сообщения → когда её прислали (правка или исходная отправка)."""


def stated_at(plan: SchedulePlan, sent: Stated) -> datetime | None:
    """Когда человек сообщил этот план. None — правка админа на сайте, она действует всегда."""
    if plan.source is Source.MANUAL:
        return plan.created_at if plan.created_by.startswith("bot:") else None
    if plan.source_version_id is None:
        return plan.created_at
    return sent.get(plan.source_version_id, plan.created_at)


async def approved_plans(session: AsyncSession, plans: Iterable[SchedulePlan]) -> set[int]:
    """Планы, чью позднюю правку админ подтвердил в инбоксе («Принять» или «Исправить»)."""
    by_parse = {p.parse_result_id: p.id for p in plans if p.parse_result_id is not None}
    if not by_parse:
        return set()
    rows = await session.scalars(
        select(ParseResultRow.id).where(
            ParseResultRow.id.in_(by_parse),
            ParseResultRow.resolution.in_([Resolution.ACCEPTED, Resolution.FIXED]),
        )
    )
    return {by_parse[r] for r in rows}


async def message_times(session: AsyncSession, plans: Iterable[SchedulePlan]) -> Stated:
    ids = {p.source_version_id for p in plans if p.source_version_id is not None}
    if not ids:
        return {}
    rows = await session.execute(
        select(RawMessageVersion.id, RawMessageVersion.edited_at, RawMessage.sent_at)
        .join(RawMessage, RawMessageVersion.raw_message_id == RawMessage.id)
        .where(RawMessageVersion.id.in_(ids))
    )
    return {vid: edited or sent for vid, edited, sent in rows}


async def plan_history(
    session: AsyncSession, plans: list[SchedulePlan]
) -> dict[int, list[SchedulePlan]]:
    """Прежние версии (и отозванные правкой сообщения) для каждого актуального плана."""
    if not plans:
        return {}
    rows = await session.scalars(
        select(SchedulePlan)
        .where(
            SchedulePlan.employee_id.in_({p.employee_id for p in plans}),
            SchedulePlan.week_start.in_({p.week_start for p in plans}),
        )
        .options(
            selectinload(SchedulePlan.days),
            selectinload(SchedulePlan.tasks),
            selectinload(SchedulePlan.source_version),
        )
    )
    by_week: dict[tuple[int, date], list[SchedulePlan]] = {}
    for r in rows:
        by_week.setdefault((r.employee_id, r.week_start), []).append(r)
    return {
        p.id: [o for o in by_week.get((p.employee_id, p.week_start), []) if o.version < p.version]
        for p in plans
    }


def change_deadline(day: date, start_sec: int | None, notice_hours: int, tz: ZoneInfo) -> datetime:
    """До какого момента правку плана дня можно прислать без подтверждения админа.

    За ``notice_hours`` до начала дня по действующему плану: план с 10:00 и 12 часов — до 22:00
    накануне. День без времени (выходной, заметка, нет плана) — до конца этого дня.
    """
    midnight = datetime.combine(day, time(), tz)
    if start_sec is None:
        return midnight + timedelta(days=1)
    return midnight + timedelta(seconds=start_sec) - timedelta(hours=notice_hours)


def plan_in_force(
    day: date,
    current: SchedulePlan,
    older: list[SchedulePlan],
    settings: AppSettings,
    sent: Stated,
    approved: set[int],
) -> tuple[SchedulePlan, PlanDay | None, SchedulePlan | None]:
    """План дня с учётом того, когда о правке предупредили.

    Версии идут по времени, когда человек их прислал. Новая версия меняет день сама, если
    пришла не позже чем за ``plan_notice_hours`` до начала дня по действующему плану. Позже —
    только после подтверждения админа в инбоксе; до тех пор считается по прежнему плану. Первый
    план недели и правки админа на сайте действуют всегда. Третье значение — свежая версия,
    которая для этого дня ещё не действует (для подсказки на сайте).
    """

    def order(p: SchedulePlan) -> tuple[datetime, int]:
        return (stated_at(p, sent) or p.created_at, p.version)

    def day_of(p: SchedulePlan) -> PlanDay | None:
        return next((d for d in p.days if d.date == day), None)

    in_force: tuple[SchedulePlan, PlanDay | None] | None = None
    for p in sorted([*older, current], key=order):
        candidate = day_of(p)
        if p is not current and candidate is None:
            continue  # версия без этого дня (другой спринт) — не про него
        when = stated_at(p, sent)
        start = in_force[1].start_sec if in_force and in_force[1] else None
        if (
            in_force is None
            or when is None
            or p.id in approved
            or when <= change_deadline(day, start, settings.plan_notice_hours, settings.tz)
            or (
                p.source_version_id is not None
                and p.source_version_id == in_force[0].source_version_id
            )  # переразбор той же версии текста, а не другая правка с тем же временем
        ):
            in_force = (p, candidate)
    assert in_force is not None
    plan, pday = in_force
    return plan, pday, None if plan is current else current


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


async def employees_for_period(session: AsyncSession, start: date, end: date) -> list[Employee]:
    """Неактивного человека сохраняем в периодах, где есть его данные."""
    from sqlalchemy import or_

    has_daily = (
        select(Daily.id)
        .where(
            Daily.employee_id == Employee.id,
            Daily.work_date.between(start, end),
            Daily.retracted_at.is_(None),
        )
        .exists()
    )
    has_plan = (
        select(SchedulePlan.id)
        .join(PlanDay)
        .where(
            SchedulePlan.employee_id == Employee.id,
            PlanDay.date.between(start, end),
            SchedulePlan.retracted_at.is_(None),
        )
        .exists()
    )
    has_status = (
        select(DayStatus.id)
        .where(
            DayStatus.employee_id == Employee.id,
            DayStatus.date.between(start, end),
            DayStatus.retracted_at.is_(None),
        )
        .exists()
    )
    return list(
        await session.scalars(
            select(Employee)
            .where(or_(Employee.is_active, has_daily, has_plan, has_status))
            .order_by(Employee.short_name)
        )
    )


async def load_cells(
    session: AsyncSession,
    settings: AppSettings,
    start: date,
    end: date,
    employee_ids: Iterable[int],
    *,
    today: date | None = None,
    extra_approved: Iterable[int] = (),
) -> dict[tuple[int, date], DayCell]:
    """Все ячейки «сотрудник × день» за диапазон, включая пустые."""
    ids = list(employee_ids)
    today = today or today_local(settings)
    from teamtime.services.history import calculation_versions, settings_on

    versions = await calculation_versions(session, end)

    plan_days: dict[tuple[int, date], tuple[SchedulePlan, PlanDay]] = {}
    late_edits: dict[tuple[int, date], SchedulePlan] = {}
    plans = await current_plans(session, start, end, ids)
    history = await plan_history(session, plans)
    every = [*plans, *(o for h in history.values() for o in h)]
    sent = await message_times(session, every)
    approved = await approved_plans(session, every)
    approved.update(extra_approved)
    for p in plans:
        days = {d.date for d in p.days} | {d.date for o in history[p.id] for d in o.days}
        for day in sorted(days):
            # Если недели двух планов пересекаются датами (длинный спринт), берём более свежий.
            key = (p.employee_id, day)
            if key in plan_days and plan_days[key][0].created_at >= p.created_at:
                continue
            used, chosen, ignored = plan_in_force(
                day, p, history[p.id], settings_on(settings, versions, day), sent, approved
            )
            if chosen is None:
                plan_days.pop(key, None)
            else:
                plan_days[key] = (used, chosen)
            if ignored is not None:
                late_edits[key] = ignored
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
                settings_on(settings, versions, day).day_rules(),
                today,
            )
            cells[key] = DayCell(emp, day, result, plan, pday, daily, status, late_edits.get(key))
    return cells
