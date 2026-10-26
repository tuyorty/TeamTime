from __future__ import annotations

from decimal import Decimal

import pytest

from teamtime.bot.feedback import fix_link
from teamtime.bot.handlers.private import parse_range
from teamtime.bot.texts import format_month, plural
from teamtime.schemas import MonthSummaryOut


@pytest.mark.parametrize(
    ("n", "word"),
    [(1, "день"), (2, "дня"), (4, "дня"), (5, "дней"), (11, "дней"), (12, "дней"), (21, "день"),
     (22, "дня"), (25, "дней"), (101, "день"), (111, "дней")],
)  # fmt: skip
def test_plural(n: int, word: str) -> None:
    assert plural(n, "день", "дня", "дней") == word


def test_month_text_mentions_bonus_and_truncation() -> None:
    s = MonthSummaryOut(
        worked_sec=150 * 3600,
        result_sec=130 * 3600,
        late_total_sec=340 * 60,
        late_count=3,
        penalty_sec=20742,
        total_sec=459300,
        norm_sec=80 * 3600,
        norm_progress=1.59,
        overtime_sec=171300,
        bonus=Decimal("29739.58"),
        hourly_rate=Decimal(625),
        days_worked=20,
        days_missing=1,
        days_no_plan=0,
        days_without_efficiency=0,
        statuses={},
    )
    text = format_month("Иванов И.И.", "Октябрь 2026", s)
    assert "Опоздания(−), штраф: 5:45" in text
    assert "премия 29 739,58 ₽" in text
    assert "Без дейлика: 1 день" in text
    assert "усечены до минут" in text


def test_fix_link() -> None:
    assert fix_link("bot", 7) == "https://t.me/bot?start=fix_7"
    assert fix_link(None, 7) is None


def test_parse_range() -> None:
    from datetime import date

    assert parse_range("28.12 - 05.01", date(2026, 12, 20)) == (
        date(2026, 12, 28),
        date(2027, 1, 5),
    )
    assert parse_range("ерунда", date(2026, 12, 20)) is None
