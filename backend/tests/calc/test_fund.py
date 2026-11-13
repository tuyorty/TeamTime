"""Примеры финансовой политики на вымышленных суммах; старые месяцы считаются отдельно."""

from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal
from fractions import Fraction

import pytest

from teamtime.calc.duration import HOUR
from teamtime.calc.fund import (
    FundCalculationError,
    SalarySegment,
    money,
    runway,
    salary,
    settlement,
    split_interval,
    vacation_days,
)
from teamtime.calc.fund_time import Calendar, Conditions, Decision, Work, segments

D = Decimal
MONTH = date(2026, 11, 1)


def segment(**changes):
    return replace(
        SalarySegment(
            key="base",
            target=D("80000"),
            share=D(1),
            full_norm=160 * HOUR,
            active_norm=160 * HOUR,
            excluded_norm=Fraction(0),
            effective=Fraction(160 * HOUR),
        ),
        **changes,
    )


@pytest.mark.parametrize(("credited", "expected"), [(140, "70000"), (160, "80000"), (180, "90000")])
def test_salary_scales_both_below_and_above_norm(credited, expected):
    _, amount = salary([segment(effective=Fraction(credited * HOUR))])
    assert amount == D(expected)


def test_target_already_includes_share():
    _, amount = salary([segment(target=D("40000"), share=D("0.5"), effective=80 * HOUR)])
    assert amount == D("40000")


def test_joining_midmonth_prorates_calendar_hours_not_calendar_days():
    parts, amount = salary([segment(active_norm=72 * HOUR, effective=72 * HOUR)])
    assert parts[0].target == D("36000")
    assert parts[0].norm == 72 * HOUR
    assert amount == D("36000")


def test_absence_reduces_norm_and_full_absence_keeps_target():
    _, amount = salary([segment(excluded_norm=40 * HOUR, effective=120 * HOUR)])
    assert amount == D("80000")
    _, full = salary([segment(excluded_norm=160 * HOUR, effective=0)])
    assert full == D("80000")
    _, partial = salary([segment(active_norm=80 * HOUR, excluded_norm=80 * HOUR, effective=0)])
    assert partial == D("40000")


@pytest.mark.parametrize(
    "changes",
    [
        {"full_norm": 0},
        {"share": D(0)},
        {"active_norm": 0, "effective": 0},
        {"excluded_norm": 161 * HOUR},
        {"excluded_norm": 160 * HOUR, "effective": HOUR},
        {"target": D("NaN")},
        {"share": D("Infinity")},
        {"raw_late": -1},
    ],
)
def test_inconsistent_data_cannot_produce_final_salary(changes):
    with pytest.raises(FundCalculationError):
        salary([segment(**changes)])


def test_trip_adds_eight_hours_without_reducing_norm():
    parts, amount = salary([segment(effective=144 * HOUR, trip_days=2)])
    assert parts[0].effective == 160 * HOUR
    assert parts[0].norm == 160 * HOUR
    assert amount == D("80000")


@pytest.mark.parametrize(
    ("late", "penalty"), [(5, 5), (12, Fraction(45, 2)), (13, Fraction(53, 2))]
)
def test_progressive_penalty_at_boundaries(late, penalty):
    parts, amount = salary([segment(raw_late=late * HOUR)])
    assert parts[0].penalty == penalty * HOUR
    assert amount == money(Fraction(80000) * (160 - penalty) / 160)


def test_salary_never_becomes_negative():
    parts, amount = salary([segment(effective=HOUR, raw_late=12 * HOUR)])
    assert parts[0].credited == 0
    assert amount == 0


def test_different_terms_and_penalty_require_lead_rule_not_proportional_guess():
    a = segment(key="first", active_norm=80 * HOUR, effective=80 * HOUR, raw_late=3 * HOUR)
    b = segment(key="second", target=D("100000"), active_norm=80 * HOUR, effective=80 * HOUR)
    with pytest.raises(FundCalculationError, match="требует решения руководителя"):
        salary([a, b])
    _, result = salary([replace(a, raw_late=0), b])
    assert result == D("90000")


def test_round_only_after_summing_exact_segments():
    a = segment(key="first", target=D("1"), full_norm=3, active_norm=1, effective=1)
    b = replace(a, key="second")
    _, amount = salary([a, b])
    assert amount == D("0.67")
    assert money(Fraction(201, 200)) == D("1.01")
    assert money(Fraction(-201, 200)) == D("-1.01")


def test_overpayment_offset_rounding_and_compensation_are_separate():
    result = settlement(
        salary_amount=D("50000"),
        received=D("35000"),
        overpayment=D("4500"),
        bonus=D("500"),
        correction=D("-123.45"),
        compensation=D("1234.56"),
        paid=D("2000"),
    )
    assert result.difference == D("15376.55")
    assert result.offset == D("4500")
    assert result.overpayment_out == 0
    assert result.supplement_before_rounding == D("10876.55")
    assert result.supplement == D("11000")
    assert result.rounding == D("123.45")
    assert result.accrued == D("12234.56")
    assert result.due == D("10234.56")


def test_negative_difference_carries_to_overpayment_and_does_not_consume_compensation():
    result = settlement(
        salary_amount=D("30000"),
        received=D("42000"),
        overpayment=D("1000"),
        compensation=D("2000.25"),
        paid=D("2100.25"),
    )
    assert result.overpayment_out == D("13000")
    assert result.offset == 0
    assert result.supplement == 0
    assert result.accrued == D("2000.25")
    assert result.due == D("-100")


@pytest.mark.parametrize(("due", "rounded"), [("0", "0"), ("1000", "1000"), ("1000.01", "2000")])
def test_round_up_only_positive_salary_supplement(due, rounded):
    result = settlement(salary_amount=D(due), received=D(0))
    assert result.supplement == D(rounded)
    assert result.overpayment_new == 0


def test_no_hidden_rounding_of_input_money():
    with pytest.raises(FundCalculationError, match="копеек"):
        settlement(salary_amount=D("0.001"), received=D(0))


def test_night_intervals_cross_month_without_losing_seconds():
    assert split_interval(date(2026, 10, 31), 23 * HOUR + 1, 2 * HOUR + 3) == [
        (date(2026, 10, 31), 23 * HOUR + 1, 86400),
        (MONTH, 0, 2 * HOUR + 3),
    ]


def calendar():
    # Искусственный проверочный календарь: не источник производственных норм.
    days = {MONTH + timedelta(days=i): (8 * HOUR if i < 20 else 0) for i in range(30)}
    return Calendar(MONTH, "fixture-v1", "Тестовый календарь", days)


def condition():
    return Conditions("base", MONTH, date(2026, 11, 30), D("80000"), D(1))


def time_segments(*, work=None, lateness=None, decisions=None, cal=None):
    return segments(
        cal or calendar(), [condition()], work or [], lateness or {}, decisions or [], MONTH
    )


def test_daily_zero_efficiency_still_conflicts_with_trip():
    with pytest.raises(FundCalculationError, match="конфликтуют"):
        time_segments(
            work=[Work(MONTH, 9 * HOUR, 10 * HOUR, 0)], decisions=[Decision(MONTH, "trip")]
        )


def test_fractional_seconds_and_night_work_are_kept():
    parts = time_segments(
        work=[
            Work(date(2026, 10, 31), 23 * HOUR, 1, 33),
            Work(date(2026, 11, 30), 23 * HOUR, HOUR, 75),
        ]
    )
    assert parts[0].effective == Fraction(33, 100) + 2700


def test_no_daily_is_not_confirmed_absence_or_penalty():
    parts = time_segments()
    assert parts[0].raw_late == 0
    assert parts[0].excluded_norm == 0
    assert parts[0].effective == 0


def test_full_missed_shift_and_waiver_before_monthly_progression():
    parts = time_segments(
        lateness={MONTH: HOUR},
        decisions=[
            Decision(MONTH + timedelta(days=1), "missed", 8 * HOUR),
            Decision(MONTH + timedelta(days=1), "waiver", 5 * HOUR),
        ],
    )
    result, _ = salary(parts)
    assert result[0].penalty == 4 * HOUR


@pytest.mark.parametrize(
    "decisions",
    [
        [Decision(MONTH, "vacation"), Decision(MONTH, "sick")],
        [Decision(MONTH, "trip"), Decision(MONTH, "trip")],
        [Decision(MONTH, "waiver", 1)],
        [Decision(MONTH, "missed")],
    ],
)
def test_decision_conflicts_block_calculation(decisions):
    with pytest.raises(FundCalculationError):
        time_segments(decisions=decisions)


def test_work_overlap_including_adjacent_daily_after_midnight_is_rejected():
    with pytest.raises(FundCalculationError, match="пересекаются"):
        time_segments(
            work=[
                Work(date(2026, 10, 31), 23 * HOUR, 2 * HOUR, 80),
                Work(MONTH, HOUR, 3 * HOUR, 80),
            ]
        )
    assert (
        time_segments(work=[Work(MONTH, HOUR, 2 * HOUR, 80), Work(MONTH, 2 * HOUR, 3 * HOUR, 80)])[
            0
        ].effective
        == 5760
    )


def test_incomplete_calendar_is_not_replaced_with_weekdays():
    cal = calendar()
    del cal.days[MONTH]
    with pytest.raises(FundCalculationError, match="все дни"):
        time_segments(cal=cal)


def test_terms_with_same_salary_and_share_do_not_split_monthly_penalty():
    a = replace(condition(), end=date(2026, 11, 15))
    b = replace(condition(), key="next", start=date(2026, 11, 16))
    parts = segments(calendar(), [a, b], [], {MONTH: 3 * HOUR, b.start: 3 * HOUR}, [], MONTH)
    assert len(parts) == 1
    result, _ = salary(parts)
    assert result[0].penalty == Fraction(87, 14) * HOUR


def test_changed_share_with_penalty_has_explicit_pending_code():
    a = replace(condition(), end=date(2026, 11, 15))
    b = replace(condition(), key="next", start=date(2026, 11, 16), share=D("0.5"))
    parts = segments(calendar(), [a, b], [], {MONTH: HOUR}, [], MONTH)
    with pytest.raises(FundCalculationError) as error:
        salary(parts)
    assert error.value.code == "penalty_allocation_pending"


def test_shortened_and_transferred_days_used_as_given_by_calendar():
    cal = calendar()
    cal.days[MONTH] = 7 * HOUR
    cal.days[MONTH + timedelta(days=20)] = HOUR
    parts = time_segments(cal=cal, decisions=[Decision(MONTH, "vacation")])
    assert parts[0].full_norm == 160 * HOUR
    assert parts[0].excluded_norm == 7 * HOUR


def test_vacation_counts_weekends_but_not_public_holidays():
    start, end = date(2026, 11, 2), date(2026, 11, 8)
    assert vacation_days(start, end, {date(2026, 11, 4)}) == {
        date(2026, 11, d) for d in (2, 3, 5, 6, 7, 8)
    }


def test_runway_uses_last_three_available_months_and_zero_is_unknown():
    assert runway(D("60000"), [D("5000000"), D("10000"), D("20000"), D("30000")]) == D(3)
    assert runway(D("60000"), [D("20000")]) == D(3)
    assert runway(D("60000"), []) is None
    assert runway(D("60000"), [D(0)]) is None
