"""Итоги месяца: золотой тест на вымышленном сотруднике и пример премии из задания."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from teamtime.calc import (
    DayRules,
    StatusKind,
    compute_day,
    format_hm,
    overtime_bonus,
    parse_hm,
    summarize_month,
)
from tests.calc.helpers import fact, note, work

TODAY = date(2026, 11, 2)


def golden_month():
    """Октябрь вымышленного сотрудника. Ожидаемые числа посчитаны вручную, без модуля calc:

    | день | план        | факт                    | e%  | часы | итог | опоздание |
    |------|-------------|-------------------------|-----|------|------|-----------|
    | 01   | 10:00-18:00 | 10:20-18:00             | 80  | 7:40 | 6:08 | 0:20      |
    | 02   | 10:00-18:00 | 9:55-18:05              | 100 | 8:10 | 8:10 | —         |
    | 03   | по вайбу    | 12:00-17:00             | 60  | 5:00 | 3:00 | без плана |
    | 05   | 9:00-17:00  | 11:00-13:00;14:00-17:30 | 70  | 5:30 | 3:51 | 2:00      |
    | 06   | 10:00-18:00 | отпуск                  |     |      |      |           |
    | 07   | 10:00-18:00 | нет дейлика             |     |      |      |           |
    | 08   | 10:00-18:00 | 13:20-19:00             | 90  | 5:40 | 5:06 | 3:20      |

    Сумма опозданий 5:40 → штраф 5:45 (5:45:42,857…). Итого 26:15 − 5:45:42,857 = 20:29:17,1…
    Норма 20:00 → переработка 0:29:17,1… × 500 ₽ = 244,05 ₽.
    """
    rules = DayRules()
    rows = [
        (1, work("10:00-18:00"), fact("10:20-18:00", e=80), None),
        (2, work("10:00-18:00"), fact("9:55-18:05", e=100), None),
        (3, note(), fact("12:00-17:00", e=60), None),
        (5, work("9:00-17:00"), fact("11:00-13:00", "14:00-17:30", e=70), None),
        (6, work("10:00-18:00"), None, StatusKind.VACATION),
        (7, work("10:00-18:00"), None, None),
        (8, work("10:00-18:00"), fact("13:20-19:00", e=90), None),
    ]
    return [compute_day(date(2026, 10, d), p, f, s, rules, TODAY) for d, p, f, s in rows]


def test_golden_month() -> None:
    m = summarize_month(golden_month(), norm=parse_hm("20:00"), hourly_rate=Decimal(500))
    assert format_hm(m.worked) == "32:00"  # Часы(+)
    assert format_hm(m.result) == "26:15"  # Часы(e%)
    assert format_hm(m.late_total) == "5:40"  # сумма опозданий
    assert m.late_count == 3
    assert format_hm(m.penalty) == "5:45"  # Опоздания(−)
    assert format_hm(m.total) == "20:29"  # Итого
    assert format_hm(m.overtime) == "0:29"
    assert m.bonus == Decimal("244.05")
    assert m.days_worked == 5
    assert m.days_missing == 1
    assert m.days_no_plan == 1
    assert m.statuses == {StatusKind.VACATION: 1}
    assert m.norm_progress == pytest.approx(73757.142857 / 72000)


def test_bonus_example_from_brief() -> None:
    """Итого 127:35, норма 80:00, ставка 625 → 47:35 × 625 = 29 739,58 ₽."""
    overtime = parse_hm("127:35") - parse_hm("80:00")
    assert format_hm(overtime) == "47:35"
    assert overtime_bonus(overtime, Decimal(625)) == Decimal("29739.58")


def test_no_overtime_no_bonus() -> None:
    m = summarize_month(golden_month(), norm=parse_hm("160:00"), hourly_rate=Decimal(625))
    assert m.overtime == 0
    assert m.bonus == Decimal("0.00")
    assert m.norm_progress < 1


def test_penalty_can_make_total_negative() -> None:
    rules = DayRules()
    days = [
        compute_day(date(2026, 10, d), work("8:00-9:00"), fact("12:00-13:00", e=100), None, rules,
                    TODAY)
        for d in range(1, 4)
    ]  # fmt: skip
    m = summarize_month(days, norm=parse_hm("10:00"), hourly_rate=Decimal(100))
    assert format_hm(m.late_total) == "12:00"
    assert format_hm(m.penalty) == "22:30"
    assert format_hm(m.total) == "-19:30"
    assert m.bonus == Decimal("0.00")


def test_empty_month() -> None:
    m = summarize_month([], norm=parse_hm("160:00"), hourly_rate=Decimal(625))
    assert (m.worked, m.result, m.penalty, m.total, m.bonus) == (0, 0, 0, 0, Decimal("0.00"))
