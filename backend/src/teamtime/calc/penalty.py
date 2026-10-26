"""Прогрессивная шкала штрафа за опоздания за месяц.

x — суммарное опоздание за месяц в часах:

    x ≤ 5        штраф = x
    5 < x ≤ 12   штраф = 5 + (x − 5) + 3·(x − 5)² / 14
    x > 12       штраф = 22,5 + 4·(x − 12)

Шкала непрерывна (при x = 12 обе ветки дают 22,5) и гладкая: наклон растёт с 1 до 4.
Все параметры настраиваются, см. ``PenaltyScale``.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction

from teamtime.calc.duration import HOUR, Seconds


@dataclass(frozen=True, slots=True)
class PenaltyScale:
    soft_limit_h: Fraction = Fraction(5)
    """До этого порога штраф равен опозданию."""
    hard_limit_h: Fraction = Fraction(12)
    """После этого порога штраф растёт линейно с наклоном ``tail_slope``."""
    quad_coef: Fraction = Fraction(3, 14)
    """Коэффициент квадратичной части между порогами."""
    hard_value_h: Fraction = Fraction(45, 2)
    """Значение штрафа на втором пороге (22,5)."""
    tail_slope: Fraction = Fraction(4)

    def penalty(self, late: Seconds | int) -> Seconds:
        """Штраф в секундах за суммарное опоздание ``late`` (секунды)."""
        x = Fraction(late) / HOUR
        if x <= 0:
            return Fraction(0)
        if x <= self.soft_limit_h:
            result = x
        elif x <= self.hard_limit_h:
            d = x - self.soft_limit_h
            result = self.soft_limit_h + d + self.quad_coef * d * d
        else:
            result = self.hard_value_h + self.tail_slope * (x - self.hard_limit_h)
        return result * HOUR

    def middle_branch_at_hard_limit(self) -> Fraction:
        d = self.hard_limit_h - self.soft_limit_h
        return self.soft_limit_h + d + self.quad_coef * d * d

    def continuity_gap_h(self) -> Fraction:
        """Разрыв шкалы на втором пороге, в часах. 0 — шкала непрерывна."""
        return self.hard_value_h - self.middle_branch_at_hard_limit()

    def slope_at_hard_limit(self) -> Fraction:
        """Наклон квадратичной ветки на втором пороге (для гладкости он равен ``tail_slope``)."""
        return 1 + 2 * self.quad_coef * (self.hard_limit_h - self.soft_limit_h)

    def validate(self) -> list[str]:
        """Проблемы конфигурации по-русски. Пустой список — всё в порядке."""
        problems: list[str] = []
        if self.soft_limit_h < 0 or self.hard_limit_h <= self.soft_limit_h:
            problems.append("Второй порог должен быть больше первого, оба не меньше нуля")
            return problems
        if self.quad_coef < 0 or self.tail_slope < 0:
            problems.append("Коэффициенты не могут быть отрицательными")
        gap = self.continuity_gap_h()
        if gap != 0:
            problems.append(
                f"Шкала разрывна на втором пороге: средняя ветка даёт "
                f"{float(self.middle_branch_at_hard_limit()):.4g} ч, а задано "
                f"{float(self.hard_value_h):.4g} ч"
            )
        return problems


DEFAULT_SCALE = PenaltyScale()
