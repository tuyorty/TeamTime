"""Отчёты для экранов: сегодня, неделя, месяц, сотрудник, планы.

Здесь только сборка: все правила расчёта живут в ``teamtime.calc``.
"""

from __future__ import annotations

import calendar
from collections import defaultdict
from collections.abc import Iterable, Sequence
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from teamtime.calc import STATUS_LABELS, DayState, MonthSummary, StatusKind, summarize_month
from teamtime.calc.duration import truncate_seconds
from teamtime.core import clock
from teamtime.db.models import (
    Daily,
    Employee,
    ParseResultRow,
    PlanDay,
    RawMessage,
    RawMessageVersion,
    Resolution,
    SchedulePlan,
    TelegramIdentity,
)
from teamtime.parsing import MessageKind, PlanDayKind
from teamtime.parsing.text import format_seconds
from teamtime.schemas import (
    DayCellOut,
    DayTotals,
    Deviation,
    EmployeeBrief,
    EmployeeDetailOut,
    EmployeeOut,
    FactOut,
    FeedItem,
    IdentityOut,
    LateDay,
    MonthHistoryPoint,
    MonthOut,
    MonthRow,
    MonthSummaryOut,
    NoteItem,
    PenaltyScaleOut,
    PlanOut,
    PlanRow,
    PlansOut,
    PlanVersionOut,
    SourceRef,
    Streaks,
    TodayOut,
    TodayRow,
    Totals,
    WeekOut,
    WeekPlanInfo,
    WeekPoint,
    WeekRow,
    WeekTasks,
)
from teamtime.services.facts import (
    DayCell,
    active_employees,
    date_range,
    load_cells,
    today_local,
)
from teamtime.services.settings import AppSettings

MONTHS = (
    "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
    "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь",
)  # fmt: skip
MONTHS_GENITIVE = (
    "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
)  # fmt: skip


def week_label(iso_week: int) -> str:
    return f"{iso_week} неделя"


def month_label(year: int, month: int) -> str:
    return f"{MONTHS[month - 1]} {year}"


def iso_week_start(iso_year: int, iso_week: int) -> date:
    return date.fromisocalendar(iso_year, iso_week, 1)


# --- ячейки --------------------------------------------------------------------------------


def plan_out(day: PlanDay) -> PlanOut:
    return PlanOut(
        kind=day.kind,
        start=day.start_sec,
        end=day.end_sec,
        planned_sec=day.planned_sec,
        intervals=[(a, b) for a, b in day.intervals],
        note=day.note,
        note_has_time=day.note_has_time,
        raw_line=day.raw_line,
    )


def fact_out(daily: Daily, result_sec: int | None) -> FactOut:
    intervals = [(i.start_sec, i.end_sec) for i in daily.intervals]
    return FactOut(
        start=intervals[0][0],
        end=intervals[-1][1],
        intervals=intervals,
        worked_sec=sum((b - a) if b >= a else 86400 - a + b for a, b in intervals),
        efficiency=daily.efficiency,
        result_sec=result_sec,
        tasks=[t.text for t in daily.tasks],
        edited=daily.edited,
        sent_at=daily.sent_at,
        source=daily.source,
    )


def cell_out(cell: DayCell) -> DayCellOut:
    r = cell.result
    plan, daily = cell.plan, cell.daily
    return DayCellOut(
        date=cell.day,
        state=r.state,
        status=cell.status.kind if cell.status else None,
        status_label=STATUS_LABELS[cell.status.kind] if cell.status else None,
        status_note=cell.status.note if cell.status else None,
        plan=plan_out(cell.plan_day) if cell.plan_day else None,
        fact=fact_out(daily, truncate_seconds(r.result) if r.result is not None else None)
        if daily
        else None,
        late_sec=r.late,
        early_leave_sec=r.early_leave,
        undertime_sec=r.undertime,
        no_plan=r.no_plan,
        flags=list(r.flags),
        source=SourceRef(
            plan_id=plan.id if plan and cell.plan_day else None,
            plan_version=plan.version if plan and cell.plan_day else None,
            plan_message_version_id=plan.source_version_id if plan and cell.plan_day else None,
            plan_raw_message_id=plan.source_version.raw_message_id
            if plan and cell.plan_day and plan.source_version
            else None,
            daily_id=daily.id if daily else None,
            daily_version=daily.version if daily else None,
            daily_message_version_id=daily.source_version_id if daily else None,
            daily_raw_message_id=daily.source_version.raw_message_id
            if daily and daily.source_version
            else None,
        ),
    )


def totals(cells: Iterable[DayCell]) -> Totals:
    t = Totals()
    for c in cells:
        r = c.result
        if r.worked is not None:
            t.worked_sec += r.worked
        if r.result is not None:
            t.result_sec += truncate_seconds(r.result)  # для недели достаточно усечения по дням
        if r.planned:
            t.planned_sec += r.planned
        if r.late:
            t.late_sec += r.late
            t.late_count += 1
        t.early_count += 1 if r.early_leave else 0
        t.undertime_count += 1 if r.undertime else 0
        t.days_worked += r.state is DayState.WORKED
        t.days_missing += r.state is DayState.MISSING
        t.days_no_plan += r.no_plan
    return t


def day_totals(day: date, cells: Sequence[DayCell]) -> DayTotals:
    return DayTotals(
        date=day,
        worked_sec=sum(c.result.worked or 0 for c in cells),
        planned_count=sum(1 for c in cells if c.result.planned),
        worked_count=sum(1 for c in cells if c.result.state is DayState.WORKED),
        late_count=sum(1 for c in cells if c.result.late),
        missing_count=sum(1 for c in cells if c.result.state is DayState.MISSING),
        absence_count=sum(1 for c in cells if c.result.state is DayState.ABSENCE),
    )


def brief(e: Employee) -> EmployeeBrief:
    return EmployeeBrief.model_validate(e)


# --- неделя --------------------------------------------------------------------------------


async def plan_versions_count(
    session: AsyncSession, keys: Iterable[tuple[int, int, int]]
) -> dict[tuple[int, int, int], int]:
    keys = list(keys)
    if not keys:
        return {}
    rows = await session.execute(
        select(SchedulePlan.employee_id, SchedulePlan.iso_year, SchedulePlan.iso_week).where(
            SchedulePlan.employee_id.in_({k[0] for k in keys}),
            SchedulePlan.iso_week.in_({k[2] for k in keys}),
        )
    )
    counts: dict[tuple[int, int, int], int] = defaultdict(int)
    for row in rows:
        counts[(row[0], row[1], row[2])] += 1
    return counts


async def week_report(
    session: AsyncSession, settings: AppSettings, iso_year: int, iso_week: int
) -> WeekOut:
    start = iso_week_start(iso_year, iso_week)
    days = list(date_range(start, start + timedelta(days=6)))
    employees = await active_employees(session)
    cells = await load_cells(session, settings, days[0], days[-1], [e.id for e in employees])
    versions = await plan_versions_count(session, [(e.id, iso_year, iso_week) for e in employees])

    rows: list[WeekRow] = []
    for e in employees:
        ecells = [cells[(e.id, d)] for d in days]
        plan = next((c.plan for c in ecells if c.plan is not None), None)
        rows.append(
            WeekRow(
                employee=brief(e),
                cells=[cell_out(c) for c in ecells],
                totals=totals(ecells),
                plan=WeekPlanInfo(
                    plan_id=plan.id,
                    version=plan.version,
                    versions=versions.get((e.id, iso_year, iso_week), 1),
                    edited=plan.edited or plan.version > 1,
                    tasks=[t.text for t in plan.tasks],
                    sprint_start=plan.sprint_start,
                    sprint_end=plan.sprint_end,
                )
                if plan
                else None,
            )
        )
    return WeekOut(
        iso_year=iso_year,
        iso_week=iso_week,
        label=week_label(iso_week),
        week_start=start,
        days=days,
        rows=rows,
        day_totals=[day_totals(d, [cells[(e.id, d)] for e in employees]) for d in days],
        totals=totals(cells.values()),
        today=today_local(settings),
    )


# --- месяц ---------------------------------------------------------------------------------


def summary_out(m: MonthSummary) -> MonthSummaryOut:
    return MonthSummaryOut(
        worked_sec=truncate_seconds(m.worked),
        result_sec=truncate_seconds(m.result),
        late_total_sec=truncate_seconds(m.late_total),
        late_count=m.late_count,
        penalty_sec=truncate_seconds(m.penalty),
        total_sec=truncate_seconds(m.total),
        norm_sec=truncate_seconds(m.norm),
        norm_progress=round(m.norm_progress, 4),
        overtime_sec=truncate_seconds(m.overtime),
        bonus=m.bonus,
        hourly_rate=m.hourly_rate,
        days_worked=m.days_worked,
        days_missing=m.days_missing,
        days_no_plan=m.days_no_plan,
        days_without_efficiency=m.days_without_efficiency,
        statuses={k.value: v for k, v in m.statuses.items()},
    )


def summarize(employee: Employee, cells: Iterable[DayCell], settings: AppSettings) -> MonthSummary:
    return summarize_month(
        (c.result for c in cells),
        norm=employee.monthly_norm_minutes * 60,
        hourly_rate=Decimal(employee.hourly_rate),
        scale=settings.penalty.scale(),
    )


def month_bounds(year: int, month: int) -> tuple[date, date]:
    return date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1])


def _weeks(cells: Sequence[DayCell]) -> list[WeekPoint]:
    by_week: dict[int, list[DayCell]] = defaultdict(list)
    for c in cells:
        by_week[c.day.isocalendar().week].append(c)
    points = []
    for week, wcells in sorted(by_week.items(), key=lambda kv: kv[1][0].day):
        t = totals(wcells)
        points.append(
            WeekPoint(
                iso_week=week,
                label=week_label(week),
                worked_sec=t.worked_sec,
                result_sec=t.result_sec,
                late_sec=t.late_sec,
            )
        )
    return points


def scale_out(settings: AppSettings) -> PenaltyScaleOut:
    scale = settings.penalty.scale()
    return PenaltyScaleOut(
        soft_limit_h=float(scale.soft_limit_h),
        hard_limit_h=float(scale.hard_limit_h),
        quad_coef=float(scale.quad_coef),
        hard_value_h=float(scale.hard_value_h),
        tail_slope=float(scale.tail_slope),
        problems=scale.validate(),
    )


async def month_report(
    session: AsyncSession, settings: AppSettings, year: int, month: int, *, history: int = 6
) -> MonthOut:
    first, last = month_bounds(year, month)
    employees = await active_employees(session)
    ids = [e.id for e in employees]
    cells = await load_cells(session, settings, first, last, ids)
    days = list(date_range(first, last))

    rows: list[MonthRow] = []
    deviations: list[Deviation] = []
    for e in employees:
        ecells = [cells[(e.id, d)] for d in days]
        late_days = [
            LateDay(
                date=c.day,
                late_sec=c.result.late,
                plan_start=c.result.plan.start or 0 if c.result.plan else 0,
                fact_start=c.result.fact.start if c.result.fact else 0,
            )
            for c in ecells
            if c.result.late
        ]
        rows.append(
            MonthRow(
                employee=EmployeeOut.model_validate(e),
                summary=summary_out(summarize(e, ecells, settings)),
                late_days=late_days,
                weeks=_weeks(ecells),
            )
        )
        for c in ecells:
            r = c.result
            for kind, value in (
                ("late", r.late),
                ("early_leave", r.early_leave),
                ("undertime", r.undertime),
            ):
                if value:
                    deviations.append(
                        Deviation(employee=brief(e), date=c.day, kind=kind, value_sec=value)
                    )
            if r.state is DayState.MISSING:
                deviations.append(
                    Deviation(employee=brief(e), date=c.day, kind="missing_daily", value_sec=None)
                )
    deviations.sort(key=lambda d: (d.value_sec is None, -(d.value_sec or 0), d.date))

    history_points: list[MonthHistoryPoint] = []
    y, m = year, month
    months: list[tuple[int, int]] = []
    for _ in range(history):
        months.append((y, m))
        y, m = (y - 1, 12) if m == 1 else (y, m - 1)
    first_data = await session.scalar(
        select(func.min(Daily.work_date)).where(Daily.retracted_at.is_(None))
    )
    for hy, hm_ in reversed(months):
        if (
            first_data
            and (hy, hm_) < (first_data.year, first_data.month)
            and (hy, hm_)
            != (
                year,
                month,
            )
        ):
            continue
        if (hy, hm_) == (year, month):
            summaries = [r.summary for r in rows]
        else:
            hf, hl = month_bounds(hy, hm_)
            hcells = await load_cells(session, settings, hf, hl, ids)
            summaries = [
                summary_out(summarize(e, [hcells[(e.id, d)] for d in date_range(hf, hl)], settings))
                for e in employees
            ]
        history_points.append(
            MonthHistoryPoint(
                year=hy,
                month=hm_,
                label=f"{MONTHS[hm_ - 1][:3]} {str(hy)[2:]}",
                worked_sec=sum(s.worked_sec for s in summaries),
                result_sec=sum(s.result_sec for s in summaries),
                total_sec=sum(s.total_sec for s in summaries),
                penalty_sec=sum(s.penalty_sec for s in summaries),
                norm_sec=sum(s.norm_sec for s in summaries),
            )
        )

    return MonthOut(
        year=year,
        month=month,
        label=month_label(year, month),
        first_day=first,
        last_day=last,
        rows=rows,
        scale=scale_out(settings),
        history=history_points,
        deviations=deviations[:20],
        complete=today_local(settings) > last,
    )


# --- сегодня -------------------------------------------------------------------------------


def _presence(cell: DayCell, now_sec: int) -> str:
    status = cell.status.kind if cell.status else None
    if status is not None and status.cancels_plan:
        return "absent"
    plan = cell.result.plan
    if status is StatusKind.REMOTE:
        return "remote"
    if plan is None or not plan.has_time or cell.result.planned is None:
        return "no_plan"
    assert plan.start is not None
    assert plan.end_abs is not None
    if now_sec < plan.start:
        return "expected_later"
    if now_sec <= plan.end_abs:
        return "on_site"
    return "left"


def feed_summary(row: ParseResultRow) -> str:
    data = row.data or {}
    if row.status.value == "failed":
        first = next((i["message"] for i in row.issues if i["severity"] == "error"), "не разобрано")
        return f"Не разобрано: {first[0].lower()}{first[1:]}"
    if row.kind is MessageKind.DAILY and data:
        d = date.fromisoformat(data["work_date"])
        spans = "; ".join(f"{format_seconds(a)}–{format_seconds(b)}" for a, b in data["intervals"])
        eff = f", e {data['efficiency']}%" if data.get("efficiency") is not None else ""
        return f"Дейлик за {d.day} {MONTHS_GENITIVE[d.month - 1]}: {spans}{eff}"
    if row.kind is MessageKind.SCHEDULE and data:
        return f"Расписание на {data['iso_week']} неделю"
    return "Сообщение"


async def feed(session: AsyncSession, limit: int = 20) -> list[FeedItem]:
    rows = await session.execute(
        select(ParseResultRow, RawMessageVersion, RawMessage)
        .join(RawMessageVersion, ParseResultRow.message_version_id == RawMessageVersion.id)
        .join(RawMessage, RawMessageVersion.raw_message_id == RawMessage.id)
        .where(ParseResultRow.is_latest, ParseResultRow.kind != MessageKind.UNKNOWN)
        .order_by(RawMessageVersion.received_at.desc(), ParseResultRow.id.desc())
        .limit(limit)
        .options(selectinload(ParseResultRow.employee))
    )
    return [
        FeedItem(
            id=pr.id,
            at=ver.edited_at or raw.sent_at,
            kind=pr.kind,
            status=pr.status,
            resolution=pr.resolution,
            employee=brief(pr.employee) if pr.employee else None,
            author_name=raw.author_name,
            summary=feed_summary(pr),
            edited=ver.version > 1,
            raw_message_id=raw.id,
        )
        for pr, ver, raw in rows
    ]


async def today_report(
    session: AsyncSession, settings: AppSettings, day: date | None = None
) -> TodayOut:
    now_local = clock.now().astimezone(settings.tz)
    day = day or now_local.date()
    now_sec = (
        now_local.hour * 3600 + now_local.minute * 60
        if day == now_local.date()
        else (86400 if day < now_local.date() else 0)
    )
    employees = await active_employees(session)
    ids = [e.id for e in employees]
    week_start = day - timedelta(days=day.weekday())
    cells = await load_cells(session, settings, week_start, week_start + timedelta(days=6), ids)

    rows = []
    counts: dict[str, int] = defaultdict(int)
    for e in employees:
        cell = cells[(e.id, day)]
        presence = _presence(cell, now_sec)
        overdue = (presence == "left" and cell.daily is None) or (
            cell.result.state is DayState.PENDING and day < now_local.date()
        )
        rows.append(
            TodayRow(
                employee=brief(e), cell=cell_out(cell), presence=presence, daily_overdue=overdue
            )
        )
        counts[presence] += 1
        counts["planned"] += 1 if cell.result.planned else 0
        counts["dailies"] += 1 if cell.daily else 0
        counts["late"] += 1 if cell.result.late else 0
        counts["awaiting_daily"] += 1 if cell.result.planned and cell.daily is None else 0
    worked = sum(cells[(e.id, day)].result.worked or 0 for e in employees)
    pulse = [
        day_totals(d, [cells[(e.id, d)] for e in employees])
        for d in date_range(week_start, week_start + timedelta(days=6))
    ]
    return TodayOut(
        date=day,
        now_sec=now_sec,
        rows=rows,
        counts=dict(counts),
        worked_sec=worked,
        feed=await feed(session),
        week_pulse=pulse,
    )


# --- сотрудник -----------------------------------------------------------------------------


def _streaks(cells: Sequence[DayCell]) -> Streaks:
    on_time = best = 0
    for c in cells:
        if c.result.state is not DayState.WORKED:
            continue
        on_time = 0 if c.result.late else on_time + 1
        best = max(best, on_time)
    dailies = 0
    for c in reversed(cells):
        if c.result.state is DayState.WORKED:
            dailies += 1
        elif c.result.state is DayState.MISSING:
            break
    return Streaks(current_on_time=on_time, best_on_time=best, current_dailies=dailies)


async def employee_report(
    session: AsyncSession,
    settings: AppSettings,
    employee: Employee,
    start: date | None = None,
    end: date | None = None,
) -> EmployeeDetailOut:
    today = today_local(settings)
    end = end or today
    start = start or (end - timedelta(days=end.weekday()) - timedelta(weeks=7))
    month_first, month_last = month_bounds(today.year, today.month)
    lo, hi = min(start, month_first), max(end, month_last)
    all_cells = await load_cells(session, settings, lo, hi, [employee.id])
    cells = [all_cells[(employee.id, d)] for d in date_range(start, end)]
    month_cells = [all_cells[(employee.id, d)] for d in date_range(month_first, month_last)]

    facts = [c.result.fact for c in cells if c.result.fact is not None]
    late_minutes = [
        (c.result.fact.start - c.result.plan.start) // 60
        for c in cells
        if c.result.fact and c.result.plan and c.result.plan.start is not None and c.result.planned
    ]

    tasks_by_week: dict[tuple[int, int], WeekTasks] = {}
    for c in cells:
        iso = c.day.isocalendar()
        wt = tasks_by_week.setdefault(
            (iso.year, iso.week),
            WeekTasks(
                iso_year=iso.year,
                iso_week=iso.week,
                label=week_label(iso.week),
                planned=[t.text for t in c.plan.tasks] if c.plan else [],
                done=[],
            ),
        )
        if not wt.planned and c.plan:
            wt.planned = [t.text for t in c.plan.tasks]
        if c.daily and c.daily.tasks:
            wt.done.append((c.day, [t.text for t in c.daily.tasks]))

    notes: list[NoteItem] = []
    for c in cells:
        if c.plan_day and c.plan_day.kind is PlanDayKind.NOTE and c.plan_day.note:
            notes.append(NoteItem(date=c.day, kind="plan_note", text=c.plan_day.note))
        if c.status:
            notes.append(
                NoteItem(
                    date=c.day,
                    kind="status",
                    text=c.status.note or STATUS_LABELS[c.status.kind],
                    status=c.status.kind,
                )
            )

    identities = await session.scalars(
        select(TelegramIdentity)
        .where(TelegramIdentity.employee_id == employee.id)
        .options(
            selectinload(TelegramIdentity.employee),
            selectinload(TelegramIdentity.suggested_employee),
        )
    )
    return EmployeeDetailOut(
        employee=EmployeeOut.model_validate(employee),
        identities=[IdentityOut.model_validate(i) for i in identities],
        start=start,
        end=end,
        days=[cell_out(c) for c in cells],
        totals=totals(cells),
        avg_start_sec=sum(f.start for f in facts) // len(facts) if facts else None,
        arrivals=[f.start for f in facts],
        late_minutes=late_minutes,
        streaks=_streaks(cells),
        weeks=_weeks(cells),
        tasks=sorted(tasks_by_week.values(), key=lambda w: (w.iso_year, w.iso_week), reverse=True),
        notes=sorted(notes, key=lambda n: n.date, reverse=True),
        month=summary_out(summarize(employee, month_cells, settings)),
    )


# --- планы ---------------------------------------------------------------------------------


def plan_version_out(plan: SchedulePlan) -> PlanVersionOut:
    return PlanVersionOut(
        id=plan.id,
        version=plan.version,
        created_at=plan.created_at,
        source=plan.source,
        created_by=plan.created_by,
        edited=plan.edited,
        retracted=plan.retracted_at is not None,
        days=[(d.date, plan_out(d)) for d in plan.days],
        tasks=[t.text for t in plan.tasks],
        message_version_id=plan.source_version_id,
        raw_message_id=plan.source_version.raw_message_id if plan.source_version else None,
    )


async def plans_report(
    session: AsyncSession, settings: AppSettings, iso_year: int, iso_week: int
) -> PlansOut:
    start = iso_week_start(iso_year, iso_week)
    days = list(date_range(start, start + timedelta(days=6)))
    employees = await active_employees(session)
    plans = await session.scalars(
        select(SchedulePlan)
        .where(SchedulePlan.iso_year == iso_year, SchedulePlan.iso_week == iso_week)
        .order_by(SchedulePlan.employee_id, SchedulePlan.version)
        .options(
            selectinload(SchedulePlan.days),
            selectinload(SchedulePlan.tasks),
            selectinload(SchedulePlan.source_version),
        )
    )
    by_emp: dict[int, list[SchedulePlan]] = defaultdict(list)
    for p in plans:
        by_emp[p.employee_id].append(p)
    cells = await load_cells(session, settings, days[0], days[-1], [e.id for e in employees])

    rows = []
    for e in employees:
        versions = by_emp.get(e.id, [])
        current = next((p for p in reversed(versions) if p.retracted_at is None), None)
        ecells = [cells[(e.id, d)] for d in days]
        rows.append(
            PlanRow(
                employee=brief(e),
                current=plan_version_out(current) if current else None,
                versions=[plan_version_out(p) for p in versions],
                done_tasks=[t.text for c in ecells if c.daily for t in c.daily.tasks],
                days_with_daily=sum(1 for c in ecells if c.daily),
                days_planned=sum(1 for c in ecells if c.result.planned),
            )
        )
    return PlansOut(
        iso_year=iso_year,
        iso_week=iso_week,
        label=week_label(iso_week),
        week_start=start,
        days=days,
        rows=rows,
    )


async def pending_inbox_count(session: AsyncSession) -> int:
    return (
        await session.scalar(
            select(func.count())
            .select_from(ParseResultRow)
            .where(ParseResultRow.is_latest, ParseResultRow.resolution == Resolution.PENDING)
        )
        or 0
    )
