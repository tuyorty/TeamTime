"""Факты периода по дейликам и действующим правилам таблицы; без оценок и рейтингов."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from datetime import date, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from teamtime.calc import DayState
from teamtime.schemas import EmployeeBrief, HighlightOccurrence, HighlightRecord, PeriodHighlights
from teamtime.services.facts import DayCell
from teamtime.services.settings import AppSettings


def _record(
    values: list[tuple[int, HighlightOccurrence]], *, earliest: bool = False
) -> HighlightRecord | None:
    if not values:
        return None
    value = min(item[0] for item in values) if earliest else max(item[0] for item in values)
    occurrences = [item for candidate, item in values if candidate == value]
    occurrences.sort(
        key=lambda item: (item.date, item.employee.id if item.employee else 0), reverse=True
    )
    return HighlightRecord(
        value_sec=value,
        occurrences=occurrences[:3],
        total_occurrences=len(occurrences),
    )


def period_highlights(
    cells: Iterable[DayCell],
    employees: dict[int, EmployeeBrief],
    today: date,
    *,
    calendar_off: set[date] | None = None,
    changed_schedule_days: int = 0,
) -> PeriodHighlights:
    """Будущие даты исключаем; при равных значениях сохраняем число всех совпадений."""
    cells = [cell for cell in cells if cell.day <= today]
    reported = [cell for cell in cells if cell.result.fact is not None]
    off_dates = (
        calendar_off
        if calendar_off is not None
        else {
            cell.day + timedelta(days=n)
            for cell in cells
            for n in (0, 1)
            if (cell.day + timedelta(days=n)).weekday() == 6
        }
    )
    evening_night = 0
    calendar_off_work = 0
    longest_series = 0
    by_employee: dict[int, list[date]] = defaultdict(list)
    for cell in reported:
        by_employee[cell.employee_id].append(cell.day)
        assert cell.result.fact
        for interval in cell.result.fact.intervals:
            end = interval.end + (86400 if interval.crosses_midnight else 0)
            for offset in (0, 1):
                if cell.day + timedelta(days=offset) in off_dates:
                    calendar_off_work += max(
                        0, min(end, (offset + 1) * 86400) - max(interval.start, offset * 86400)
                    )
            for base in (-86400, 0, 86400):
                evening_night += max(
                    0, min(end, base + 30 * 3600) - max(interval.start, base + 20 * 3600)
                )
    for days in by_employee.values():
        run = 0
        previous = None
        for day in sorted(set(days)):
            run = run + 1 if previous is not None and day == previous + timedelta(days=1) else 1
            longest_series = max(longest_series, run)
            previous = day
    comparable = [cell for cell in reported if cell.result.late is not None]
    worked = sum(cell.result.worked or 0 for cell in reported)
    starts, finishes, durations, lateness = [], [], [], []
    daily_work: dict[date, int] = defaultdict(int)
    participants: dict[date, int] = defaultdict(int)
    for cell in reported:
        fact = cell.result.fact
        assert fact is not None
        occurrence = HighlightOccurrence(date=cell.day, employee=employees[cell.employee_id])
        starts.append((fact.start, occurrence))
        finishes.append((fact.end_abs, occurrence))
        durations.append((cell.result.worked or 0, occurrence))
        if cell.result.late:
            lateness.append((cell.result.late, occurrence))
        daily_work[cell.day] += cell.result.worked or 0
        participants[cell.day] += 1
    return PeriodHighlights(
        calendar_off_sec=calendar_off_work,
        evening_night_sec=evening_night,
        long_days=sum((cell.result.worked or 0) > 10 * 3600 for cell in reported),
        longest_daily_series=longest_series,
        changed_schedule_days=changed_schedule_days,
        reported_days=len(reported),
        employees_reported=len({cell.employee_id for cell in reported}),
        worked_sec=worked,
        tasks_reported=sum(len(cell.daily.tasks) for cell in reported if cell.daily),
        average_day_sec=worked // len(reported) if reported else None,
        comparable_days=len(comparable),
        on_time_days=sum(cell.result.late == 0 for cell in comparable),
        missing_days=sum(cell.result.state is DayState.MISSING for cell in cells),
        earliest_start=_record(starts, earliest=True),
        latest_finish=_record(finishes),
        longest_day=_record(durations),
        largest_lateness=_record(lateness),
        busiest_day=_record(
            [
                (duration, HighlightOccurrence(date=day, participants=participants[day]))
                for day, duration in daily_work.items()
            ]
        ),
    )


async def highlights_for(
    session: AsyncSession,
    settings: AppSettings,
    cells: Iterable[DayCell],
    employees: dict[int, EmployeeBrief],
    today: date,
) -> PeriodHighlights:
    """Выходные берём из действовавших правил, изменения считаем по версиям дней."""
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from teamtime.db.models import SchedulePlan
    from teamtime.services.history import calculation_versions, settings_on

    cells = list(cells)
    if not cells:
        return period_highlights([], employees, today)
    start, end = min(c.day for c in cells), max(c.day for c in cells)
    versions = await calculation_versions(session, end + timedelta(days=1))
    off_dates = set()
    for day in {cell.day + timedelta(days=n) for cell in cells for n in (0, 1)}:
        rules = settings_on(settings, versions, day)
        if day.weekday() in rules.weekly_off or day in rules.holidays:
            off_dates.add(day)
    plans = await session.scalars(
        select(SchedulePlan)
        .where(
            SchedulePlan.employee_id.in_(employees),
            SchedulePlan.week_start.between(start - timedelta(days=6), end),
        )
        .options(selectinload(SchedulePlan.days))
        .order_by(SchedulePlan.employee_id, SchedulePlan.week_start, SchedulePlan.version)
    )
    previous: dict[tuple[int, date], dict[date, tuple[object, object, object]]] = {}
    changed = set()
    for plan in plans:
        key = (plan.employee_id, plan.week_start)
        current: dict[date, tuple[object, object, object]] = {
            day.date: (day.kind, day.intervals, day.note) for day in plan.days
        }
        if key in previous:
            old = previous[key]
            for day in current.keys() | old.keys():
                if start <= day <= min(end, today) and current.get(day) != old.get(day):
                    changed.add((plan.employee_id, day))
        previous[key] = current
    return period_highlights(
        cells, employees, today, calendar_off=off_dates, changed_schedule_days=len(changed)
    )
