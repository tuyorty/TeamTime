"""Даты навигации: компактные callback-данные и переходы между периодами."""

from __future__ import annotations

import calendar
from datetime import date, timedelta

MIN_DATE = date(2000, 1, 1)
MAX_DATE = date(2100, 12, 31)


def date_key(day: date) -> str:
    return day.strftime("%Y%m%d")


def read_date(value: str) -> date:
    if len(value) != 8 or not value.isascii() or not value.isdigit():
        raise ValueError("Некорректная дата")
    day = date.fromisoformat(value)
    if not MIN_DATE <= day <= MAX_DATE:
        raise ValueError("Дата вне диапазона 2000–2100")
    return day


def shift_period(day: date, view: str, step: int) -> date | None:
    """При смене месяца сохраняем день, если он существует в новом месяце."""
    if view == "month":
        index = day.year * 12 + day.month - 1 + step
        year, month = divmod(index, 12)
        month += 1
        shifted = date(year, month, min(day.day, calendar.monthrange(year, month)[1]))
    else:
        shifted = day + timedelta(days=step * (7 if view == "week" else 1))
    return shifted if MIN_DATE <= shifted <= MAX_DATE else None
