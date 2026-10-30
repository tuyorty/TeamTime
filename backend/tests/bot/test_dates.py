"""Календарные границы навигации и размер callback-данных Telegram."""

from datetime import date

import pytest

from teamtime.bot.dates import date_key, read_date, shift_period
from teamtime.bot.keyboards import calendar_menu, report_menu


@pytest.mark.parametrize(
    ("day", "view", "step", "expected"),
    [
        (date(2026, 1, 31), "month", 1, date(2026, 2, 28)),
        (date(2028, 1, 31), "month", 1, date(2028, 2, 29)),
        (date(2026, 12, 31), "month", 1, date(2027, 1, 31)),
        (date(2026, 1, 1), "month", -1, date(2025, 12, 1)),
        (date(2026, 12, 31), "day", 1, date(2027, 1, 1)),
        (date(2026, 12, 28), "week", 1, date(2027, 1, 4)),
        (date(2000, 1, 1), "day", -1, None),
        (date(2100, 12, 31), "month", 1, None),
    ],
)
def test_shift_period(day, view, step, expected) -> None:
    assert shift_period(day, view, step) == expected


@pytest.mark.parametrize("value", ["20260230", "19991231", "21010101", "2026-10-26", "wrong"])
def test_read_date_rejects_invalid_or_out_of_range(value: str) -> None:
    with pytest.raises(ValueError):
        read_date(value)


def test_calendar_has_leap_day_and_buttons_fit_telegram_limit() -> None:
    day = date(2028, 2, 29)
    keyboard = calendar_menu("month", day, day.replace(day=1), day, 2**63 - 1)
    buttons = [button for row in keyboard.inline_keyboard for button in row]
    assert any(button.text == "[29]" for button in buttons)
    assert all(len(button.callback_data.encode()) <= 64 for button in buttons)
    assert read_date(date_key(day)) == day


def test_period_navigation_keeps_employee_and_handles_date_boundaries() -> None:
    keyboard = report_menu("day", date(2000, 1, 1), date(2026, 10, 26), employee_id=2**63 - 1)
    buttons = [button for row in keyboard.inline_keyboard for button in row]
    assert not any(button.text.startswith("‹") for button in buttons)
    assert all(len(button.callback_data.encode()) <= 64 for button in buttons)
