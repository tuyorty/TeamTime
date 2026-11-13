"""Чистые расчёты фонда: точное время, календарная норма и деньги на руки.

Расчёт не проводит выплаты и не меняет переплаты. Применение результата — отдельная
идемпотентная транзакция закрытия месяца. Историческая модель calc.month сохранена.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal, localcontext
from fractions import Fraction

from teamtime.calc.duration import HOUR
from teamtime.calc.penalty import DEFAULT_SCALE, PenaltyScale

RULESET = "fund-2026-11-v1"
START = date(2026, 11, 1)
ZERO = Decimal("0.00")
KOPECK = Decimal("0.01")


class FundCalculationError(ValueError):
    """Неполные или конфликтующие данные нельзя подменять догадкой."""

    def __init__(self, message: str, code: str = "invalid_input") -> None:
        super().__init__(message)
        self.code = code


def decimal(value: Fraction | int | Decimal) -> Decimal:
    if isinstance(value, Fraction):
        with localcontext() as ctx:
            ctx.prec = 40
            return Decimal(value.numerator) / Decimal(value.denominator)
    return Decimal(value)


def money(value: Decimal | Fraction) -> Decimal:
    if isinstance(value, Fraction):
        # Округление рационального числа без промежуточного округления деления.
        numerator = abs(value.numerator) * 100
        cents, rest = divmod(numerator, value.denominator)
        cents += int(rest * 2 >= value.denominator)
        return Decimal(cents if value >= 0 else -cents).scaleb(-2)
    if not value.is_finite():
        raise FundCalculationError("Сумма должна быть конечным числом")
    return value.quantize(KOPECK, rounding=ROUND_HALF_UP)


def month_start(day: date) -> date:
    return day.replace(day=1)


def next_month(day: date) -> date:
    return date(day.year + day.month // 12, day.month % 12 + 1, 1)


@dataclass(frozen=True)
class SalarySegment:
    """Датированный участок условий; длительности заданы точными секундами."""

    key: str
    target: Decimal
    share: Decimal
    full_norm: int
    active_norm: int
    excluded_norm: Fraction
    effective: Fraction
    trip_days: int = 0
    raw_late: Fraction = Fraction(0)


@dataclass(frozen=True)
class SegmentResult:
    key: str
    target: Decimal
    norm: Fraction
    effective: Fraction
    penalty: Fraction
    credited: Fraction
    salary: Decimal


def salary(
    segments: list[SalarySegment],
    scale: PenaltyScale = DEFAULT_SCALE,
) -> tuple[list[SegmentResult], Decimal]:
    """Способ распределения штрафа между условиями ещё требует согласования правила."""
    if not segments:
        raise FundCalculationError("Не заданы условия участия")
    if len({s.key for s in segments}) != len(segments):
        raise FundCalculationError("Участки условий повторяются")
    if scale.validate():
        raise FundCalculationError("Некорректная шкала штрафа")
    if any(s.raw_late < 0 for s in segments):
        raise FundCalculationError("Опоздание не может быть отрицательным")
    penalty = scale.penalty(sum((s.raw_late for s in segments), Fraction(0)))
    if penalty and len(segments) > 1:
        raise FundCalculationError(
            "Распределение месячного штрафа требует решения руководителя",
            code="penalty_allocation_pending",
        )
    results: list[SegmentResult] = []
    exact_salary = Fraction(0)
    for segment in segments:
        s = segment
        if not s.target.is_finite() or not s.share.is_finite():
            raise FundCalculationError("Условия должны содержать конечные числа")
        if s.target < 0 or s.share <= 0 or s.full_norm <= 0:
            raise FundCalculationError("Нужны целевая сумма, положительная ставка и календарь")
        if not 0 <= s.active_norm <= s.full_norm:
            raise FundCalculationError("Период участия выходит за календарную норму месяца")
        before = Fraction(s.share) * s.active_norm
        if (
            not 0 <= s.excluded_norm <= before
            or s.effective < 0
            or s.trip_days < 0
            or s.raw_late < 0
        ):
            raise FundCalculationError("Отрицательные или противоречивые часы")
        target = Fraction(s.target) * Fraction(s.active_norm, s.full_norm)
        norm = before - s.excluded_norm
        effective = s.effective + s.trip_days * 8 * HOUR
        part_penalty = penalty if len(segments) == 1 else Fraction(0)
        credited = max(Fraction(0), effective - part_penalty)
        if not norm:
            if before <= 0 or s.excluded_norm != before:
                raise FundCalculationError(
                    "Нулевая норма не подтверждена согласованным отсутствием"
                )
            if effective or part_penalty:
                raise FundCalculationError("Полное отсутствие конфликтует с работой или штрафом")
            amount = target
        else:
            amount = target * credited / norm
        exact_salary += amount
        results.append(
            SegmentResult(
                s.key, decimal(target), norm, effective, part_penalty, credited, decimal(amount)
            )
        )
    return results, money(exact_salary)


@dataclass(frozen=True)
class FundAmounts:
    salary: Decimal
    bonus: Decimal
    correction: Decimal
    received: Decimal
    overpayment_in: Decimal
    difference: Decimal
    offset: Decimal
    overpayment_new: Decimal
    overpayment_out: Decimal
    supplement_before_rounding: Decimal
    supplement: Decimal
    rounding: Decimal
    compensation: Decimal
    accrued: Decimal
    paid: Decimal
    due: Decimal


def settlement(
    *,
    salary_amount: Decimal,
    received: Decimal,
    overpayment: Decimal = ZERO,
    bonus: Decimal = ZERO,
    correction: Decimal = ZERO,
    compensation: Decimal = ZERO,
    paid: Decimal = ZERO,
) -> FundAmounts:
    """Компенсации не погашаются переплатой; превышение выплаты не скрывается."""
    values = (salary_amount, received, overpayment, bonus, correction, compensation, paid)
    if any(not v.is_finite() for v in values):
        raise FundCalculationError("Сумма должна быть конечным числом")
    if min(salary_amount, overpayment, bonus, compensation, paid) < 0:
        raise FundCalculationError("Отрицательная сумма требует отдельной корректировки")
    if any(money(v) != v for v in values):
        raise FundCalculationError(
            "Денежные входные суммы должны быть указаны с точностью до копеек"
        )
    difference = money(salary_amount + bonus + correction - received)
    offset = min(overpayment, max(ZERO, difference))
    new = max(ZERO, -difference)
    before_rounding = max(ZERO, difference - overpayment)
    rounded = (before_rounding / 1000).to_integral_value(rounding=ROUND_CEILING) * 1000
    accrued = rounded + compensation
    return FundAmounts(
        money(salary_amount),
        money(bonus),
        money(correction),
        money(received),
        money(overpayment),
        difference,
        money(offset),
        money(new),
        money(overpayment - offset + new),
        money(before_rounding),
        money(rounded),
        money(rounded - before_rounding),
        money(compensation),
        money(accrued),
        money(paid),
        money(accrued - paid),
    )


def split_interval(day: date, start: int, end: int) -> list[tuple[date, int, int]]:
    """Ночной интервал разбивается на календарные даты без потери секунд."""
    if not 0 <= start < 86400 or not 0 <= end <= 108000 or start == end:
        raise FundCalculationError("Некорректный рабочий интервал")
    if end < start:
        end += 86400
    if end <= 86400:
        return [(day, start, end)]
    return [(day, start, 86400), (day + timedelta(days=1), 0, end - 86400)]


def vacation_days(start: date, end: date, holidays: set[date]) -> set[date]:
    """Выходные входят в отпуск, нерабочие праздничные дни — нет."""
    if end < start:
        raise FundCalculationError("Конец отпуска раньше начала")
    return {start + timedelta(days=i) for i in range((end - start).days + 1)} - holidays


def runway(free: Decimal, monthly_cash_expenses: list[Decimal]) -> Decimal | None:
    """Запас по фактическим расходам; займы и внутренние переводы исключает журнал."""
    recent = monthly_cash_expenses[-3:]
    if not recent or sum(recent) <= 0:
        return None
    return money(free * len(recent) / sum(recent))
