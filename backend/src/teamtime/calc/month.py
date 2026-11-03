"""Итоги месяца: Часы(+), Часы(e%), опоздания, штраф, Итого, норма, переработка и премия.

День относится к месяцу по своей дате, а не по неделе.
"""

from __future__ import annotations

import calendar
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from fractions import Fraction

from teamtime.calc.day import DayResult, DayRules, DayState, StatusKind
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
    """Норма после исключения рабочих дней отпуска и командировки."""
    contract_norm: Seconds
    """Полная договорная норма, от которой считается оклад."""
    norm_reduction: Seconds
    norm_working_days: int
    norm_excluded_days: int
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
        return float(self.total / self.norm) if self.norm else float(self.total >= 0)


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
    rules: DayRules = DayRules(),
) -> MonthSummary:
    days = list(days)
    contract_norm = Fraction(norm)
    working_days: set[date] = set()
    if days:
        first = days[0].day.replace(day=1)
        if any((d.day.year, d.day.month) != (first.year, first.month) for d in days):
            raise ValueError("Для итога месяца нужны дни одного месяца")
        working_days = {
            date(first.year, first.month, n)
            for n in range(1, calendar.monthrange(first.year, first.month)[1] + 1)
            if date(first.year, first.month, n).weekday() not in rules.weekly_off
            and date(first.year, first.month, n) not in rules.holidays
        }
    excluded_days = {
        d.day
        for d in days
        if d.day in working_days and d.status in {StatusKind.VACATION, StatusKind.BUSINESS_TRIP}
    }
    reduction = (
        contract_norm * len(excluded_days) / len(working_days) if working_days else Fraction(0)
    )
    effective_norm = contract_norm - reduction
    worked = sum((Fraction(d.worked) for d in days if d.worked is not None), Fraction(0))
    result = sum((d.result for d in days if d.result is not None), Fraction(0))
    late_total = sum((Fraction(d.late) for d in days if d.late), Fraction(0))
    late_count = sum(1 for d in days if d.late)
    penalty = scale.penalty(late_total)
    total = result - penalty
    overtime = max(Fraction(0), total - effective_norm)
    statuses = Counter(d.status for d in days if d.status is not None)
    return MonthSummary(
        worked=worked,
        result=result,
        late_total=late_total,
        late_count=late_count,
        penalty=penalty,
        total=total,
        norm=effective_norm,
        contract_norm=contract_norm,
        norm_reduction=reduction,
        norm_working_days=len(working_days),
        norm_excluded_days=len(excluded_days),
        overtime=overtime,
        bonus=overtime_bonus(overtime, hourly_rate),
        hourly_rate=hourly_rate,
        days_worked=sum(1 for d in days if d.state is DayState.WORKED),
        days_missing=sum(1 for d in days if d.state is DayState.MISSING),
        days_no_plan=sum(1 for d in days if d.no_plan),
        days_without_efficiency=sum(1 for d in days if d.worked is not None and d.result is None),
        statuses=dict(statuses),
    )
