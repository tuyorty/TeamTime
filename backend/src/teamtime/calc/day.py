"""Расчёт одного дня сотрудника: план, факт, итог, опоздание, ранний уход, недоработка.

Правила исходной таблицы с одной поправкой: если плана нет («по вайбу», выходной),
опоздания нет. В таблице пустой план превращал всё время прихода в опоздание.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum
from fractions import Fraction

from teamtime.calc.duration import Seconds
from teamtime.parsing.types import SECONDS_PER_DAY, Interval, PlanDayKind


class StatusKind(StrEnum):
    """Статус дня, который задают вручную (админ или сотрудник через бота)."""

    VACATION = "vacation"
    SICK = "sick"
    REMOTE = "remote"
    DAYOFF = "dayoff"
    """Отгул."""
    OFF = "off"
    """Выходной, назначенный вручную."""
    ABSENT = "absent"
    """«Не приду сегодня»."""

    @property
    def cancels_plan(self) -> bool:
        """Отменяет ли статус план: в такой день нет опозданий и недоработок."""
        return self is not StatusKind.REMOTE


STATUS_LABELS: dict[StatusKind, str] = {
    StatusKind.VACATION: "Отпуск",
    StatusKind.SICK: "Больничный",
    StatusKind.REMOTE: "Удалёнка",
    StatusKind.DAYOFF: "Отгул",
    StatusKind.OFF: "Выходной",
    StatusKind.ABSENT: "Не придёт",
}


class DayState(StrEnum):
    """Сводное состояние дня для цвета ячейки."""

    WORKED = "worked"
    """Есть дейлик."""
    ABSENCE = "absence"
    """Отпуск, больничный, отгул, «не приду»."""
    OFF = "off"
    """Выходной по плану, по календарю или праздник."""
    MISSING = "missing"
    """План был, день прошёл, дейлика нет."""
    PENDING = "pending"
    """План есть, день ещё не закончился (или в будущем)."""
    UNPLANNED = "unplanned"
    """Ни плана со временем, ни дейлика: ничего не ожидалось."""


@dataclass(frozen=True, slots=True)
class PlanInput:
    kind: PlanDayKind
    intervals: tuple[Interval, ...] = ()
    note: str | None = None

    @property
    def has_time(self) -> bool:
        return self.kind is PlanDayKind.WORK and bool(self.intervals)

    @property
    def start(self) -> int | None:
        return self.intervals[0].start if self.has_time else None

    @property
    def end_abs(self) -> int | None:
        return _abs_end(self.intervals) if self.has_time else None

    @property
    def planned_seconds(self) -> int | None:
        return sum(i.duration for i in self.intervals) if self.has_time else None


@dataclass(frozen=True, slots=True)
class FactInput:
    intervals: tuple[Interval, ...]
    efficiency: int | None
    """Процент 0–100 или None, если не указан."""

    @property
    def start(self) -> int:
        return self.intervals[0].start

    @property
    def end_abs(self) -> int:
        return _abs_end(self.intervals)

    @property
    def worked_seconds(self) -> int:
        return sum(i.duration for i in self.intervals)


def _abs_end(intervals: tuple[Interval, ...]) -> int:
    """Конец последнего интервала в секундах от полуночи дня; после полуночи — больше суток."""
    last = intervals[-1]
    crossed = any(i.crosses_midnight for i in intervals)
    return last.end + SECONDS_PER_DAY if crossed and last.end <= intervals[0].start else last.end


@dataclass(frozen=True, slots=True)
class DayRules:
    late_tolerance: int = 0
    """Допуск опоздания, секунды. Опоздание в пределах допуска не считается."""
    early_tolerance: int = 0
    undertime_tolerance: int = 0
    weekly_off: frozenset[int] = frozenset({6})
    """Дни недели (0 — пн), которые выходные, если в плане не сказано иное."""
    holidays: frozenset[date] = frozenset()


@dataclass(frozen=True, slots=True)
class DayResult:
    day: date
    state: DayState
    plan: PlanInput | None
    fact: FactInput | None
    status: StatusKind | None

    worked: int | None
    """Часы дня (сумма интервалов), секунды. None — нет дейлика (это не 0)."""
    result: Seconds | None
    """Итог = Часы × e%. None — нет дейлика или не указана эффективность."""
    late: int | None
    """Опоздание, секунды. None — не применимо (нет плана со временем, нет факта, статус)."""
    early_leave: int | None
    undertime: int | None
    planned: int | None
    no_plan: bool
    """Был дейлик, но не было плана со временем: опоздание и недоработка не считаются."""
    flags: tuple[str, ...] = field(default=())

    @property
    def is_late(self) -> bool:
        return bool(self.late)


def compute_day(
    day: date,
    plan: PlanInput | None,
    fact: FactInput | None,
    status: StatusKind | None,
    rules: DayRules,
    today: date,
) -> DayResult:
    """Посчитать день. ``today`` нужен, чтобы отличить «ещё не прислал» от «не прислал»."""
    cancels = status is not None and status.cancels_plan
    holiday = day in rules.holidays
    effective_plan = None if cancels else plan
    planned_work = effective_plan is not None and effective_plan.has_time and not holiday

    worked = fact.worked_seconds if fact else None
    result: Seconds | None = None
    if fact is not None and fact.efficiency is not None:
        result = Fraction(fact.worked_seconds) * fact.efficiency / 100

    late = early = under = None
    flags: list[str] = []
    if fact is not None and planned_work and effective_plan is not None:
        assert effective_plan.start is not None
        assert effective_plan.end_abs is not None
        late = _over(fact.start - effective_plan.start, rules.late_tolerance)
        early = _over(effective_plan.end_abs - fact.end_abs, rules.early_tolerance)
        planned_s = effective_plan.planned_seconds or 0
        under = _over(planned_s - fact.worked_seconds, rules.undertime_tolerance)
        for name, value in (("late", late), ("early_leave", early), ("undertime", under)):
            if value:
                flags.append(name)
    if fact is not None and fact.efficiency is None:
        flags.append("no_efficiency")
    if fact is not None and any(i.crosses_midnight for i in fact.intervals):
        flags.append("overnight")
    if plan is not None and plan.kind is PlanDayKind.NOTE:
        flags.append("plan_note")

    no_plan = fact is not None and not planned_work and not cancels
    if no_plan:
        flags.append("no_plan")

    if fact is not None:
        state = DayState.WORKED
        if cancels:
            flags.append("worked_on_absence")
    elif cancels:
        state = DayState.ABSENCE
    elif planned_work:
        state = DayState.MISSING if day < today else DayState.PENDING
        if state is DayState.MISSING:
            flags.append("missing_daily")
    elif (
        holiday
        or (plan is not None and plan.kind is PlanDayKind.OFF)
        or (plan is None and day.weekday() in rules.weekly_off)
        or status is StatusKind.OFF
    ):
        state = DayState.OFF
    else:
        state = DayState.UNPLANNED

    return DayResult(
        day=day,
        state=state,
        plan=plan,
        fact=fact,
        status=status,
        worked=worked,
        result=result,
        late=late,
        early_leave=early,
        undertime=under,
        planned=effective_plan.planned_seconds if planned_work and effective_plan else None,
        no_plan=no_plan,
        flags=tuple(flags),
    )


def _over(value: int, tolerance: int) -> int:
    """Отклонение с допуском: в пределах допуска — 0, сверх допуска — целиком."""
    return value if value > tolerance else 0
