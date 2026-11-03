"""Снижение нормы по рабочему календарю без уменьшения договорного оклада."""

from datetime import date
from decimal import Decimal
from fractions import Fraction

import pytest

from teamtime.calc import DayRules, DayState, StatusKind, compute_day, summarize_month
from teamtime.services.finance import amounts
from tests.calc.helpers import fact, note, work

RULES = DayRules(weekly_off=frozenset({5, 6}))
TODAY = date(2026, 3, 1)


def day(n, status=None, daily=None, rules=RULES, plan=None):
    return compute_day(date(2026, 2, n), plan or work("10:00-18:00"), daily, status, rules, TODAY)


@pytest.mark.parametrize("status", [StatusKind.VACATION, StatusKind.BUSINESS_TRIP])
def test_two_weeks_reduce_80_to_40_without_changing_salary(status):
    days = [day(n, status) for n in range(2, 16)]
    days += [day(n, daily=fact("10:00-15:00")) for n in [16, 17, 18, 19, 20, 23, 24, 25, 26]]
    summary = summarize_month(days, norm=80 * 3600, hourly_rate=Decimal(500), rules=RULES)
    assert summary.contract_norm == 80 * 3600
    assert summary.norm == summary.norm_reduction == 40 * 3600
    assert (summary.norm_excluded_days, summary.norm_working_days) == (10, 20)
    assert summary.worked == summary.result == summary.total == 45 * 3600
    assert summary.overtime == 5 * 3600
    pay = amounts(summary, Decimal(0))
    assert pay.salary == Decimal("40000.00")
    assert pay.overtime_pay == Decimal("2500.00")


def test_holiday_and_weekends_are_excluded_from_both_counts():
    rules = DayRules(weekly_off=RULES.weekly_off, holidays=frozenset({date(2026, 2, 2)}))
    summary = summarize_month(
        [day(n, StatusKind.VACATION, rules=rules) for n in range(1, 16)],
        norm=80 * 3600,
        hourly_rate=Decimal(500),
        rules=rules,
    )
    assert (summary.norm_excluded_days, summary.norm_working_days) == (9, 19)
    assert summary.norm == Fraction(80 * 3600 * 10, 19)


def test_only_explicit_vacation_and_trip_reduce_norm_once_per_working_date():
    days = [
        day(2, StatusKind.VACATION),
        day(2, StatusKind.VACATION),
        day(3, StatusKind.BUSINESS_TRIP),
    ]
    days += [
        day(n, s)
        for n, s in enumerate(
            [
                StatusKind.SICK,
                StatusKind.DAYOFF,
                StatusKind.OFF,
                StatusKind.ABSENT,
                StatusKind.REMOTE,
            ],
            4,
        )
    ]
    days += [day(9, plan=note("отпуск"))]
    summary = summarize_month(days, norm=80 * 3600, hourly_rate=Decimal(500), rules=RULES)
    assert summary.norm_excluded_days == 3
    assert summary.norm == 68 * 3600


@pytest.mark.parametrize("efficiency", [None, 85])
def test_trip_keeps_source_fact_but_excludes_hours_and_deviations(efficiency):
    daily = fact("12:00-19:00", e=efficiency)
    trip = day(2, StatusKind.BUSINESS_TRIP, daily)
    assert trip.fact is daily
    assert trip.state is DayState.ABSENCE
    assert trip.worked == trip.result == 0
    assert trip.planned is trip.late is trip.early_leave is trip.undertime is None
    assert "business_trip_excluded" in trip.flags
    assert "no_efficiency" not in trip.flags
    summary = summarize_month([trip], norm=80 * 3600, hourly_rate=Decimal(500), rules=RULES)
    assert summary.days_worked == summary.days_without_efficiency == 0
    restored = day(2, daily=daily)
    assert restored.worked == 7 * 3600
    assert restored.late == 2 * 3600


def test_full_month_absence_has_zero_norm_and_full_salary():
    summary = summarize_month(
        [day(n, StatusKind.VACATION) for n in range(1, 29)],
        norm=80 * 3600,
        hourly_rate=Decimal(500),
        rules=RULES,
    )
    assert summary.norm == summary.overtime == summary.bonus == 0
    assert summary.norm_progress == 1
    assert amounts(summary, Decimal(0)).salary == Decimal("40000.00")


def test_calendar_without_working_days_does_not_divide_by_zero():
    rules = DayRules(weekly_off=frozenset(range(7)))
    summary = summarize_month(
        [day(2, StatusKind.VACATION)], norm=3600, hourly_rate=Decimal(500), rules=rules
    )
    assert summary.norm == summary.contract_norm == 3600
    assert summary.norm_working_days == summary.norm_excluded_days == 0


def test_summary_rejects_days_from_different_months():
    march = compute_day(date(2026, 3, 1), None, None, None, RULES, TODAY)
    with pytest.raises(ValueError, match="одного месяца"):
        summarize_month([day(2), march], norm=3600, hourly_rate=Decimal(500), rules=RULES)
