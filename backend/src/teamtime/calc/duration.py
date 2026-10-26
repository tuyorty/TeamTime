"""Длительности в точных секундах и их показ «Ч:ММ» с усечением, как в исходной таблице."""

from __future__ import annotations

from fractions import Fraction

Seconds = Fraction
"""Длительность в секундах, точная дробь."""

HOUR = 3600


def hours(value: Fraction | int) -> Seconds:
    """Часы → секунды."""
    return Fraction(value) * HOUR


def hm(h: int, m: int = 0, s: int = 0) -> Seconds:
    """Удобный конструктор для тестов и настроек: hm(9, 30) == 9:30."""
    return Fraction(h * HOUR + m * 60 + s)


def truncate_seconds(value: Fraction) -> int:
    """Целые секунды с отбрасыванием дробной части (к нулю)."""
    return int(value)


def format_hm(value: Fraction | int | None, *, empty: str = "—") -> str:
    """«Ч:ММ» с усечением до минут к нулю. Отрицательные значения со знаком минус."""
    if value is None:
        return empty
    total = int(Fraction(value))  # к нулю
    sign = "-" if total < 0 else ""
    total = abs(total)
    return f"{sign}{total // HOUR}:{total % HOUR // 60:02d}"


def format_hms(value: Fraction | int) -> str:
    total = int(Fraction(value))
    sign = "-" if total < 0 else ""
    total = abs(total)
    return f"{sign}{total // HOUR}:{total % HOUR // 60:02d}:{total % 60:02d}"


def parse_hm(text: str) -> Seconds:
    """«9:30», «47:35», «4:01:48» → секунды. Для тестов и ввода в админке."""
    parts = [int(p) for p in text.strip().split(":")]
    if not 1 <= len(parts) <= 3:
        raise ValueError(f"ожидалось Ч:ММ[:СС], получено {text!r}")
    h, m, s = ([*parts, 0, 0])[:3]
    if m > 59 or s > 59 or h < 0:
        raise ValueError(f"неверное время {text!r}")
    return hm(h, m, s)
