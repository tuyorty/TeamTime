"""Расчёт дня: итог, опоздание, ранний уход, недоработка, состояния."""

from __future__ import annotations

from datetime import date

import pytest

from teamtime.calc import (
    DayRules,
    DayState,
    StatusKind,
    compute_day,
    format_hm,
    format_hms,
)
from teamtime.calc.duration import parse_hm
from tests.calc.helpers import fact, note, off, work

DAY = date(2026, 10, 21)  # среда
TODAY = date(2026, 10, 26)
RULES = DayRules()


def day(plan=None, f=None, status=None, rules=RULES, on=DAY, today=TODAY):
    return compute_day(on, plan, f, status, rules, today)


class TestResult:
    def test_hours_times_efficiency_from_brief(self) -> None:
        r = day(work("10:00-20:00"), fact("10:00-19:30", e=80))
        assert format_hm(r.worked) == "9:30"
        assert format_hm(r.result) == "7:36"

    def test_fractional_minutes_are_exact(self) -> None:
        r = day(work("10:00-17:00"), fact("10:00-16:43", e=60))
        assert format_hms(r.result) == "4:01:48"
        assert r.result == parse_hm("4:01:48")

    def test_truncation_to_minutes(self) -> None:
        r = day(None, fact("10:00-10:59", e=99))  # 58:24.6
        assert format_hm(r.result) == "0:58"

    def test_hours_sum_intervals_not_first_to_last(self) -> None:
        r = day(work("13:00-19:00"), fact("13:30-15:30", "17:30-18:40", e=100))
        assert format_hm(r.worked) == "3:10"

    def test_no_efficiency_means_no_result(self) -> None:
        r = day(work("10:00-18:00"), fact("10:00-18:00", e=None))
        assert r.worked == 8 * 3600
        assert r.result is None
        assert "no_efficiency" in r.flags

    def test_zero_efficiency_is_zero_not_missing(self) -> None:
        r = day(work("10:00-18:00"), fact("10:00-18:00", e=0))
        assert r.result == 0


class TestLateness:
    @pytest.mark.parametrize(
        ("plan_span", "fact_span", "late"),
        [
            ("10:00-18:00", "10:00-18:00", "0:00"),
            ("10:00-18:00", "09:40-18:00", "0:00"),
            ("10:00-18:00", "10:01-18:00", "0:01"),
            ("10:00-18:00", "10:20-18:00", "0:20"),
            ("12:00-18:00", "15:40-20:00", "3:40"),
            ("6:00-14:00", "06:00-14:00", "0:00"),
        ],
    )
    def test_late(self, plan_span: str, fact_span: str, late: str) -> None:
        r = day(work(plan_span), fact(fact_span))
        assert format_hm(r.late) == late

    def test_late_uses_first_interval_start(self) -> None:
        r = day(work("10:00-18:00"), fact("10:30-12:00", "13:00-18:00"))
        assert format_hm(r.late) == "0:30"

    def test_tolerance_within_is_zero_beyond_is_full(self) -> None:
        rules = DayRules(late_tolerance=5 * 60)
        assert day(work("10:00-18:00"), fact("10:05-18:00"), rules=rules).late == 0
        assert format_hm(day(work("10:00-18:00"), fact("10:06-18:00"), rules=rules).late) == "0:06"

    @pytest.mark.parametrize("plan", [None, note(), note("по вайбу с 16:30 до вечера"), off()])
    def test_no_plan_means_no_lateness(self, plan) -> None:
        """Ошибка исходной таблицы: пустой план превращал всё время прихода в опоздание."""
        r = day(plan, fact("15:40-20:00"))
        assert r.late is None
        assert r.undertime is None
        assert r.no_plan is True
        assert r.state is DayState.WORKED

    def test_no_fact_means_no_lateness(self) -> None:
        assert day(work("10:00-18:00"), None).late is None

    @pytest.mark.parametrize(
        "status",
        [StatusKind.VACATION, StatusKind.SICK, StatusKind.DAYOFF, StatusKind.OFF,
         StatusKind.ABSENT],
    )  # fmt: skip
    def test_absence_status_cancels_lateness(self, status: StatusKind) -> None:
        r = day(work("10:00-18:00"), fact("12:00-18:00"), status)
        assert r.late is None
        assert "worked_on_absence" in r.flags
        assert r.no_plan is False

    def test_remote_keeps_plan(self) -> None:
        r = day(work("10:00-18:00"), fact("10:30-18:00"), StatusKind.REMOTE)
        assert format_hm(r.late) == "0:30"

    def test_holiday_cancels_plan(self) -> None:
        r = day(work("10:00-18:00"), fact("12:00-14:00"), rules=DayRules(holidays=frozenset({DAY})))
        assert r.late is None
        assert r.no_plan is True


class TestEarlyLeaveAndUndertime:
    def test_early_leave(self) -> None:
        r = day(work("10:00-18:00"), fact("10:00-17:15"))
        assert format_hm(r.early_leave) == "0:45"
        assert format_hm(r.undertime) == "0:45"

    def test_staying_late_is_not_early(self) -> None:
        r = day(work("10:00-18:00"), fact("10:00-19:00"))
        assert r.early_leave == 0
        assert r.undertime == 0

    def test_undertime_from_breaks(self) -> None:
        r = day(work("10:00-18:00"), fact("10:00-12:00", "14:00-18:00"))
        assert r.early_leave == 0
        assert format_hm(r.undertime) == "2:00"
        assert "undertime" in r.flags

    def test_overnight_fact_end_is_next_day(self) -> None:
        r = day(work("20:00-23:00"), fact("20:00-01:00"))
        assert r.early_leave == 0
        assert r.worked == 5 * 3600
        assert "overnight" in r.flags


class TestStates:
    def test_missing_daily_in_the_past(self) -> None:
        r = day(work("10:00-18:00"), None)
        assert r.state is DayState.MISSING
        assert r.worked is None  # нет дейлика — не ноль
        assert "missing_daily" in r.flags

    def test_pending_today(self) -> None:
        r = day(work("10:00-18:00"), None, on=TODAY)
        assert r.state is DayState.PENDING

    def test_absence(self) -> None:
        assert day(work("10:00-18:00"), None, StatusKind.SICK).state is DayState.ABSENCE

    def test_planned_off(self) -> None:
        assert day(off(), None).state is DayState.OFF

    def test_sunday_without_plan_is_off(self) -> None:
        assert day(None, None, on=date(2026, 10, 25)).state is DayState.OFF

    def test_saturday_without_plan_is_unplanned(self) -> None:
        """Суббота по умолчанию рабочая по плану сотрудника: без плана — ничего не ожидалось."""
        assert day(None, None, on=date(2026, 10, 24)).state is DayState.UNPLANNED

    def test_note_without_fact_is_unplanned(self) -> None:
        assert day(note(), None).state is DayState.UNPLANNED

    def test_zero_hours_differs_from_no_daily(self) -> None:
        r = day(work("10:00-18:00"), fact("10:00-10:00"))
        assert r.worked == 0
        assert r.state is DayState.WORKED
