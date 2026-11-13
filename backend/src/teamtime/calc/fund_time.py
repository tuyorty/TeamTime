"""Подготовка времени для фонда без догадок о пропусках, отпусках и календаре."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from fractions import Fraction
from typing import Literal

from teamtime.calc.duration import HOUR
from teamtime.calc.fund import FundCalculationError, SalarySegment, next_month, split_interval


@dataclass(frozen=True)
class Calendar:
    """Подтверждённая версия календаря; нулевые дни также должны быть перечислены."""

    month: date
    version: str
    source: str
    days: dict[date, int]
    holidays: frozenset[date] = frozenset()

    def validate(self) -> None:
        end = next_month(self.month)
        expected = {self.month + timedelta(days=i) for i in range((end - self.month).days)}
        if self.month.day != 1 or not self.source.strip() or not self.version.strip():
            raise FundCalculationError("Не указаны месяц, версия или источник календаря")
        if set(self.days) != expected:
            raise FundCalculationError("В календаре должны присутствовать все дни месяца")
        if any(type(v) is not int or not 0 <= v <= 8 * HOUR for v in self.days.values()):
            raise FundCalculationError("Норма дня должна быть целым числом секунд от 0 до 8 часов")
        if sum(self.days.values()) <= 0:
            raise FundCalculationError("Календарь не содержит положительной нормы месяца")
        if not self.holidays <= expected or any(self.days[d] for d in self.holidays):
            raise FundCalculationError("Праздники должны быть нерабочими днями этого месяца")


@dataclass(frozen=True)
class Conditions:
    key: str
    start: date
    end: date
    target: Decimal
    share: Decimal


@dataclass(frozen=True)
class Work:
    """Только актуальные подтверждённые интервалы; эффективность указана в процентах."""

    day: date
    start: int
    end: int
    efficiency: int


@dataclass(frozen=True)
class Decision:
    """Подтверждённые решения, а не свободный текст расписания или отсутствие дейлика."""

    day: date
    kind: Literal["vacation", "sick", "trip", "missed", "waiver"]
    seconds: int = 0


def segments(
    calendar: Calendar,
    conditions: list[Conditions],
    work: list[Work],
    lateness: dict[date, int],
    decisions: list[Decision],
    participation_start: date,
    participation_end: date | None = None,
) -> list[SalarySegment]:
    """Ночные часы относятся к своей календарной дате, штраф считается позже за месяц."""
    calendar.validate()
    month = calendar.month
    end = next_month(month)
    active_end = min(participation_end or end - timedelta(days=1), end - timedelta(days=1))
    active_start = max(participation_start, month)
    if active_end < active_start:
        raise FundCalculationError("Нет периода участия в выбранном месяце")
    active = {active_start + timedelta(days=i) for i in range((active_end - active_start).days + 1)}
    by_day: dict[date, Conditions] = {}
    if len({c.key for c in conditions}) != len(conditions):
        raise FundCalculationError("Идентификаторы условий повторяются")
    for c in conditions:
        if not c.target.is_finite() or not c.share.is_finite() or c.target < 0 or c.share <= 0:
            raise FundCalculationError("Неверная целевая сумма или доля ставки")
        if c.end < c.start:
            raise FundCalculationError("Конец действия условий раньше начала")
        for d in active:
            if c.start <= d <= c.end:
                if d in by_day:
                    raise FundCalculationError("Условия оплаты пересекаются")
                by_day[d] = c
    if set(by_day) != active:
        raise FundCalculationError("Не для всех дней участия заданы условия оплаты")

    intervals: dict[date, list[tuple[int, int]]] = {}
    effective: dict[date, Fraction] = {}
    for w in work:
        if not 0 <= w.efficiency <= 100:
            raise FundCalculationError("Эффективность должна быть от 0 до 100 процентов")
        for day, start, finish in split_interval(w.day, w.start, w.end):
            if not month <= day < end:
                continue
            if day not in active:
                raise FundCalculationError("Есть работа вне подтверждённого периода участия")
            previous = intervals.setdefault(day, [])
            if any(start < b and finish > a for a, b in previous):
                raise FundCalculationError("Фактические рабочие интервалы пересекаются")
            previous.append((start, finish))
            effective[day] = effective.get(day, Fraction(0)) + Fraction(
                (finish - start) * w.efficiency, 100
            )

    states: dict[date, set[str]] = {}
    raw = dict(lateness)
    if any(d not in active or type(v) is not int or v < 0 for d, v in raw.items()):
        raise FundCalculationError(
            "Опоздание должно относиться к дню участия и быть неотрицательным"
        )
    waivers: dict[date, int] = {}
    for decision in decisions:
        d, kind = decision.day, decision.kind
        if kind not in {"vacation", "sick", "trip", "missed", "waiver"}:
            raise FundCalculationError("Неизвестный вид решения")
        if d not in active or decision.seconds < 0:
            raise FundCalculationError(
                "Решение выходит за период участия или содержит неверное время"
            )
        kinds = states.setdefault(d, set())
        if kind in kinds:
            raise FundCalculationError("Решение для дня продублировано")
        kinds.add(kind)
        if kind == "waiver":
            waivers[d] = decision.seconds
        elif kind == "missed":
            if decision.seconds <= 0 or raw.get(d, 0):
                raise FundCalculationError(
                    "Полный пропуск требует длительности плана без опоздания"
                )
            raw[d] = decision.seconds
        elif decision.seconds:
            raise FundCalculationError("Длительность для этого вида решения не задаётся")
    for day, kinds in states.items():
        exclusive = kinds - {"waiver"}
        if len(exclusive) > 1 or (exclusive and day in intervals):
            raise FundCalculationError("Отсутствие, командировка или пропуск конфликтуют с фактом")
        if kinds & {"vacation", "sick", "trip"} and (raw.get(day, 0) or "waiver" in kinds):
            raise FundCalculationError("Согласованный статус дня конфликтует с опозданием")
    for d, seconds in waivers.items():
        if seconds > raw.get(d, 0):
            raise FundCalculationError("Исключение больше исходного опоздания или пропуска")
        raw[d] = raw.get(d, 0) - seconds

    # Смена источников или описания не создаёт новый участок оплаты, если C и s те же.
    groups: list[tuple[Conditions, set[date]]] = []
    for d in sorted(by_day):
        c = by_day[d]
        if groups and (groups[-1][0].target, groups[-1][0].share) == (c.target, c.share):
            groups[-1][1].add(d)
        else:
            groups.append((c, {d}))
    result: list[SalarySegment] = []
    for c, days in groups:
        if not c.share.is_finite() or c.share <= 0:
            raise FundCalculationError("Доля ставки должна быть положительной")
        result.append(
            SalarySegment(
                key=f"{c.key}:{min(days).isoformat()}",
                target=c.target,
                share=c.share,
                full_norm=sum(calendar.days.values()),
                active_norm=sum(calendar.days[d] for d in days),
                excluded_norm=Fraction(c.share)
                * sum(
                    calendar.days[d] for d in days if states.get(d, set()) & {"vacation", "sick"}
                ),
                effective=sum((effective.get(d, Fraction(0)) for d in days), Fraction(0)),
                trip_days=sum("trip" in states.get(d, set()) for d in days),
                raw_late=Fraction(sum(raw.get(d, 0) for d in days)),
            )
        )
    return result
