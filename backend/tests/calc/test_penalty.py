"""Прогрессивная шкала штрафа: золотые значения из исходной таблицы."""

from __future__ import annotations

from fractions import Fraction

import pytest

from teamtime.calc import DEFAULT_SCALE, PenaltyScale, format_hm, parse_hm


@pytest.mark.parametrize(
    ("late", "penalty"),
    [
        ("0:00", "0:00"),
        ("2:17", "2:17"),
        ("5:00", "5:00"),
        ("5:20", "5:21"),
        ("5:40", "5:45"),
        ("6:10", "6:27"),
        ("6:45", "7:24"),
        ("12:00", "22:30"),
        ("13:00", "26:30"),
    ],
)
def test_golden(late: str, penalty: str) -> None:
    assert format_hm(DEFAULT_SCALE.penalty(parse_hm(late))) == penalty


def test_exact_values_at_thresholds() -> None:
    assert DEFAULT_SCALE.penalty(parse_hm("5:00")) == 5 * 3600
    assert DEFAULT_SCALE.penalty(parse_hm("12:00")) == Fraction(45, 2) * 3600


def test_scale_is_continuous_and_smooth_with_defaults() -> None:
    assert DEFAULT_SCALE.continuity_gap_h() == 0
    assert DEFAULT_SCALE.slope_at_hard_limit() == DEFAULT_SCALE.tail_slope
    assert DEFAULT_SCALE.validate() == []


def test_scale_is_monotonic() -> None:
    values = [DEFAULT_SCALE.penalty(m * 60) for m in range(0, 20 * 60, 7)]
    assert values == sorted(values)


def test_negative_late_is_zero() -> None:
    assert DEFAULT_SCALE.penalty(-100) == 0


def test_validate_reports_discontinuity() -> None:
    bad = PenaltyScale(quad_coef=Fraction(1, 7))
    problems = bad.validate()
    assert len(problems) == 1
    assert "разрывна" in problems[0]


def test_validate_reports_wrong_thresholds() -> None:
    assert PenaltyScale(soft_limit_h=Fraction(12), hard_limit_h=Fraction(5)).validate()
