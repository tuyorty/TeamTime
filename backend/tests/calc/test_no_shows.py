"""Невыход появляется только после подтверждения, а не из-за отсутствия дейлика."""

from datetime import date
from decimal import Decimal
from fractions import Fraction
from unittest.mock import AsyncMock

import pytest

from teamtime.calc import DayRules, DayState, StatusKind, compute_day
from teamtime.calc.month import summarize_month
from teamtime.calc.no_show import confirmed_shift_end
from teamtime.calc.penalty import DEFAULT_SCALE
from teamtime.services import finance, fund_config, fund_time_view, reports
from teamtime.services.facts import DayCell
from tests.calc.helpers import fact, off, work

DAY = date(2026, 10, 21)
TODAY = date(2026, 10, 26)


def test_missing_daily_alone_never_adds_lateness():
    result = compute_day(DAY, work("10:00-18:00"), None, None, DayRules(), TODAY)
    assert result.state is DayState.MISSING
    assert result.late is None
    assert "no_show_confirmed" not in result.flags


def test_confirmed_no_show_uses_snapshot_even_when_plan_was_changed_to_off():
    result = compute_day(
        DAY, off(), None, None, DayRules(), TODAY, confirmed_no_show_seconds=7 * 3600
    )
    assert result.state is DayState.ABSENCE
    assert result.worked == 0 and result.result == 0
    assert result.planned == result.late == 7 * 3600
    assert result.flags == ("no_show_confirmed",)
    summary = summarize_month([result], norm=160 * 3600, hourly_rate=Decimal(500))
    assert summary.late_total == 7 * 3600
    assert summary.penalty == DEFAULT_SCALE.penalty(Fraction(7 * 3600))
    assert summary.days_worked == summary.days_missing == 0


def test_later_daily_uses_actual_lateness_and_marks_confirmation_conflict():
    result = compute_day(
        DAY,
        work("10:00-18:00"),
        fact("10:30-18:00", e=100),
        None,
        DayRules(),
        TODAY,
        confirmed_no_show_seconds=8 * 3600,
    )
    assert result.late == 1800
    assert result.worked == 7.5 * 3600
    assert "no_show_conflict" in result.flags
    assert "no_show_confirmed" not in result.flags


def test_approved_absence_suspends_confirmation_instead_of_double_penalty():
    result = compute_day(
        DAY,
        work("10:00-18:00"),
        None,
        StatusKind.SICK,
        DayRules(),
        TODAY,
        confirmed_no_show_seconds=8 * 3600,
    )
    assert result.late is None
    assert result.state is DayState.ABSENCE
    assert "no_show_conflict" in result.flags


def test_holiday_suspends_previous_confirmation():
    result = compute_day(
        DAY,
        work("10:00-18:00"),
        None,
        None,
        DayRules(holidays=frozenset({DAY})),
        TODAY,
        confirmed_no_show_seconds=8 * 3600,
    )
    assert result.late is None
    assert result.planned is None
    assert result.state is DayState.OFF
    assert result.flags == ("no_show_conflict",)


def month_with_confirmed_no_show():
    days = [
        compute_day(
            date(2026, 10, n),
            work("08:00-19:00" if n == 4 else "09:00-19:00"),
            fact("09:00-19:00"),
            None,
            DayRules(),
            TODAY,
        )
        for n in range(1, 5)
    ]
    days.append(
        compute_day(DAY, off(), None, None, DayRules(), TODAY, confirmed_no_show_seconds=7 * 3600)
    )
    return summarize_month(days, norm=20 * 3600, hourly_rate=Decimal(500))


def test_no_show_and_actual_lateness_share_one_monthly_scale_and_only_reduce_overtime_pay():
    summary = month_with_confirmed_no_show()
    assert summary.late_total == 8 * 3600  # 1 час обычного опоздания + 7 часов невыхода.
    assert summary.penalty == Fraction(139, 14) * 3600  # Шкала применяется один раз к 8 часам.
    assert summary.worked == 40 * 3600
    money = finance.amounts(summary, Decimal("1000.00"))
    assert money.salary == Decimal("10000.00")  # Полный оклад по действующему правилу.
    assert money.overtime_pay == Decimal("5035.71")
    assert money.total == Decimal("16035.71")


async def test_inactive_fund_does_not_replace_no_show_summary(monkeypatch):
    monkeypatch.setattr(fund_config, "FUND_AVAILABLE", False)
    monkeypatch.setattr(
        fund_config,
        "load",
        AsyncMock(return_value=fund_config.FundConfig(module_enabled=True, enabled=True)),
    )
    session = AsyncMock()
    original = reports.summary_out(month_with_confirmed_no_show())
    assert await fund_time_view.adapt(session, 1, date(2026, 11, 1), original) is original
    session.get.assert_not_called()


@pytest.mark.parametrize("confirmed", [True, False])
def test_no_show_breaks_streaks_but_approved_absence_does_not(confirmed):
    cells = []
    for number in (18, 19, 20, 21):
        day = date(2026, 10, number)
        absence = number == 20
        result = compute_day(
            day,
            work("10:00-18:00"),
            None if absence else fact("10:00-18:00"),
            StatusKind.SICK if absence and not confirmed else None,
            DayRules(),
            TODAY,
            confirmed_no_show_seconds=8 * 3600 if absence and confirmed else None,
        )
        cells.append(DayCell(1, day, result, None, None, None, None))
    at_absence = reports._streaks(cells[:3])
    assert at_absence.current_on_time == (0 if confirmed else 2)
    assert at_absence.current_dailies == (0 if confirmed else 2)
    after = reports._streaks(cells)
    assert after.current_on_time == (1 if confirmed else 3)
    assert after.current_dailies == (1 if confirmed else 3)
    assert after.best_on_time == (2 if confirmed else 3)


@pytest.mark.parametrize(
    ("spans", "end"),
    [
        (("09:00-12:00", "15:00-18:00"), 18 * 3600),
        (("15:00-18:00", "09:00-12:00"), None),
        (("09:00-14:00", "13:00-18:00"), None),
        (("22:00-02:00", "03:00-05:00"), 29 * 3600),
        (("22:00-24:00", "00:00-02:00"), 26 * 3600),
        (("22:00-02:00", "01:00-04:00"), None),
        (("22:00-23:00", "00:00-02:00"), None),
    ],
)
def test_confirmation_requires_unambiguous_nonoverlapping_shift(spans, end):
    assert confirmed_shift_end(work(*spans)) == end
