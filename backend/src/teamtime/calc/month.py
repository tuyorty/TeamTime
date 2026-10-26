"""Итоги месяца: Часы(+), Часы(e%), опоздания, штраф, Итого, норма, переработка и премия.

День относится к месяцу по своей дате, а не по неделе.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from fractions import Fraction

from teamtime.calc.day import DayResult, DayState, StatusKind
from teamtime.calc.duration import HOUR, Seconds
from teamtime.calc.penalty import DEFAULT_SCALE, PenaltyScale

KOPECK = Decimal("0.01")


@dataclass(frozen=True, slots=True)
class MonthSummary:
    worked: Seconds
    """Часы(+): сумма часов по дням."""
    result: Seconds
    """Часы(e%): сумма итогов по дням."""
    late_total: Seconds
    """Сумма опозданий за месяц (x в шкале штрафа)."""
    late_count: int
    """Дней с опозданием больше нуля."""
    penalty: Seconds
    """Опоздания(−): штраф по прогрессивной шкале от суммы опозданий."""
    total: Seconds
    """Итого = Часы(e%) − Опоздания(−)."""
    norm: Seconds
    overtime: Seconds
    """Переработка = max(0, Итого − норма)."""
    bonus: Decimal
    """Премия за переработку, ₽: переработка в часах × ставка."""
    hourly_rate: Decimal
    days_worked: int
    days_missing: int
    days_no_plan: int
    days_without_efficiency: int
    statuses: dict[StatusKind, int]

    @property
    def norm_progress(self) -> float:
        """Выполнение нормы, доля (1.0 — ровно норма). По Итого, как в таблице."""
        return float(self.total / self.norm) if self.norm else 0.0


def overtime_bonus(overtime: Seconds, hourly_rate: Decimal) -> Decimal:
    """Премия в рублях: точные часы переработки × ставка, до копеек по ROUND_HALF_UP."""
    if overtime <= 0 or hourly_rate <= 0:
        return Decimal("0.00")
    frac = Fraction(overtime) / HOUR
    value = Decimal(frac.numerator) * hourly_rate / Decimal(frac.denominator)
    return value.quantize(KOPECK, rounding=ROUND_HALF_UP)


def summarize_month(
    days: Iterable[DayResult],
    *,
    norm: Seconds | int,
    hourly_rate: Decimal,
    scale: PenaltyScale = DEFAULT_SCALE,
) -> MonthSummary:
    days = list(days)
    worked = sum((Fraction(d.worked) for d in days if d.worked is not None), Fraction(0))
    result = sum((d.result for d in days if d.result is not None), Fraction(0))
    late_total = sum((Fraction(d.late) for d in days if d.late), Fraction(0))
    late_count = sum(1 for d in days if d.late)
    penalty = scale.penalty(late_total)
    total = result - penalty
    overtime = max(Fraction(0), total - Fraction(norm))
    statuses = Counter(d.status for d in days if d.status is not None)
    return MonthSummary(
        worked=worked,
        result=result,
        late_total=late_total,
        late_count=late_count,
        penalty=penalty,
        total=total,
        norm=Fraction(norm),
        overtime=overtime,
        bonus=overtime_bonus(overtime, hourly_rate),
        hourly_rate=hourly_rate,
        days_worked=sum(1 for d in days if d.state is DayState.WORKED),
        days_missing=sum(1 for d in days if d.state is DayState.MISSING),
        days_no_plan=sum(1 for d in days if d.no_plan),
        days_without_efficiency=sum(1 for d in days if d.worked is not None and d.result is None),
        statuses=dict(statuses),
    )
