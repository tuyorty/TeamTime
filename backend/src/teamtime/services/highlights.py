"""Факты периода по дейликам и действующим правилам табеля; без оценок и рейтингов."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from datetime import date

from teamtime.calc import DayState
from teamtime.schemas import EmployeeBrief, HighlightOccurrence, HighlightRecord, PeriodHighlights
from teamtime.services.facts import DayCell


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
    cells: Iterable[DayCell], employees: dict[int, EmployeeBrief], today: date
) -> PeriodHighlights:
    """Будущие даты исключаем; при равных значениях сохраняем число всех совпадений."""
    cells = [cell for cell in cells if cell.day <= today]
    reported = [cell for cell in cells if cell.result.fact is not None]
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
