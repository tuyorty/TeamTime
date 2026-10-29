from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from html.parser import HTMLParser

import pytest

from teamtime.bot.feedback import fix_link
from teamtime.bot.handlers.private import parse_range
from teamtime.bot.replies import report_parts
from teamtime.bot.texts import format_month, format_reminder, format_today, plural
from teamtime.schemas import DayCellOut, EmployeeBrief, MonthSummaryOut, TodayOut, TodayRow


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
    assert "Штраф за месяц: <b>5:45</b>" in text
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


def test_large_team_report_is_split_without_breaking_html_or_losing_people() -> None:
    class BalancedHTML(HTMLParser):
        def __init__(self):
            super().__init__()
            self.tags = []

        def handle_starttag(self, tag, attrs):
            assert tag in {"b", "i", "code"}
            self.tags.append(tag)

        def handle_endtag(self, tag):
            assert self.tags.pop() == tag

    day = date(2026, 10, 26)
    cell = DayCellOut(
        date=day,
        state="off",
        status=None,
        status_label=None,
        status_note=None,
        plan=None,
        fact=None,
        late_sec=None,
        early_leave_sec=None,
        undertime_sec=None,
        no_plan=False,
        flags=[],
        source={},
    )
    rows = [
        TodayRow(
            employee=EmployeeBrief(
                id=index,
                full_name="Вымышленный",
                short_name=f"Сотрудник {index} <&> 🔧",
                position="",
                color="",
                is_active=True,
            ),
            cell=cell,
            presence="off",
            daily_overdue=False,
        )
        for index in range(180)
    ]
    text = format_today(
        TodayOut(
            date=day,
            now_sec=12 * 3600,
            rows=rows,
            counts={"off": 180},
            worked_sec=0,
            feed=[],
            week_pulse=[],
        )
    )
    parts = report_parts(text)
    assert len(parts) > 1
    assert "&lt;&amp;&gt;" in text
    assert "Выходной · 180" in text
    for part in parts:
        assert len(part.encode("utf-16-le")) // 2 <= 3600
        parser = BalancedHTML()
        parser.feed(part)
        assert parser.tags == []
    assert sum(part.count("• <b>Сотрудник") for part in parts) == 180


def test_reminder_keeps_work_date_and_escapes_name() -> None:
    text = format_reminder(
        "Вымышленный <&>",
        date(2026, 10, 26),
        datetime.fromisoformat("2026-10-27T02:00:00+05:00"),
        15,
    )
    assert "Вымышленный &lt;&amp;&gt;" in text
    assert "26.10.2026" in text and "27.10 в 02:00" in text
    assert "15 минут" in text and "/fix" in text
