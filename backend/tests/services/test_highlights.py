"""Факты периода: реальные интервалы, ночные смены, равные рекорды и пустые данные."""

from datetime import date

from teamtime.calc import DayRules, FactInput, PlanInput, compute_day
from teamtime.db.models import Daily, DailyTask
from teamtime.parsing import Interval, PlanDayKind
from teamtime.schemas import EmployeeBrief
from teamtime.services.facts import DayCell
from teamtime.services.highlights import period_highlights

TODAY = date(2026, 10, 29)
PEOPLE = {
    employee_id: EmployeeBrief(
        id=employee_id,
        short_name=name,
        full_name=name,
        position="",
        color="#008060",
        is_active=True,
    )
    for employee_id, name in ((1, "Иванов И.И."), (2, "Петров П.П."))
}


def cell(
    employee_id: int,
    day: int,
    intervals: tuple[tuple[int, int], ...] = (),
    plan: tuple[int, int] | None = None,
    tasks: int = 0,
) -> DayCell:
    work_date = date(2026, 10, day)
    fact = (
        FactInput(tuple(Interval(start * 3600, end * 3600) for start, end in intervals), 80)
        if intervals
        else None
    )
    planned = (
        PlanInput(PlanDayKind.WORK, (Interval(plan[0] * 3600, plan[1] * 3600),)) if plan else None
    )
    return DayCell(
        employee_id=employee_id,
        day=work_date,
        result=compute_day(work_date, planned, fact, None, DayRules(), TODAY),
        plan=None,
        plan_day=None,
        daily=Daily(tasks=[DailyTask(position=i, text=f"Задача {i}") for i in range(tasks)])
        if fact
        else None,
        status=None,
    )


def test_intervals_night_shift_missing_and_future_days() -> None:
    result = period_highlights(
        [
            cell(1, 26, ((9, 12), (13, 18)), (9, 18), 2),
            cell(2, 26, ((10, 17),), (9, 17), 1),
            cell(1, 27, ((23, 2),), (22, 2), 1),
            cell(2, 27, ((8, 12),)),
            cell(2, 28, plan=(9, 18)),
            cell(1, 30, ((7, 23),), (6, 23), 20),
        ],
        PEOPLE,
        TODAY,
    )
    assert (result.reported_days, result.employees_reported, result.worked_sec) == (4, 2, 22 * 3600)
    assert result.average_day_sec == 5 * 3600 + 30 * 60
    assert result.tasks_reported == 4
    assert (result.comparable_days, result.on_time_days, result.missing_days) == (3, 1, 1)
    assert result.earliest_start and result.earliest_start.value_sec == 8 * 3600
    assert result.earliest_start.occurrences[0].employee == PEOPLE[2]
    assert result.latest_finish and result.latest_finish.value_sec == 26 * 3600
    assert result.latest_finish.occurrences[0].date == date(2026, 10, 27)
    assert result.longest_day and result.longest_day.value_sec == 8 * 3600
    assert result.largest_lateness and result.largest_lateness.value_sec == 3600
    assert result.largest_lateness.total_occurrences == 2
    assert result.busiest_day and result.busiest_day.value_sec == 15 * 3600
    assert result.busiest_day.occurrences[0].participants == 2


def test_empty_period_has_no_invented_records() -> None:
    result = period_highlights([cell(1, 30, ((7, 23),))], PEOPLE, TODAY)
    assert result.reported_days == result.employees_reported == result.worked_sec == 0
    assert result.average_day_sec is None
    assert result.earliest_start is result.latest_finish is result.longest_day is None
    assert result.largest_lateness is result.busiest_day is None


def test_equal_records_keep_total_and_only_three_examples() -> None:
    result = period_highlights(
        [cell(1, day, ((9, 18),), (9, 18)) for day in range(20, 26)], PEOPLE, TODAY
    )
    assert result.earliest_start and result.earliest_start.total_occurrences == 6
    assert [item.date.day for item in result.earliest_start.occurrences] == [25, 24, 23]
    assert result.largest_lateness is None
    assert result.comparable_days == result.on_time_days == 6
