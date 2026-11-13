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
    BUSINESS_TRIP = "business_trip"
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
    StatusKind.BUSINESS_TRIP: "Командировка",
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
    """Отпуск, больничный, отгул, «не приду» или подтверждённый невыход."""
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
    interval_efficiencies: tuple[int | None, ...] = ()

    @property
    def effective_seconds(self) -> Fraction | None:
        """Разная эффективность отрезков суммируется без промежуточного округления."""
        values = self.interval_efficiencies or (self.efficiency,) * len(self.intervals)
        if len(values) != len(self.intervals) or any(e is None for e in values):
            return None
        return sum(
            (
                Fraction(i.duration * e, 100)
                for i, e in zip(self.intervals, values, strict=True)
                if e is not None
            ),
            Fraction(0),
        )

    @property
    def start(self) -> int:
        return self.intervals[0].start

    @property
    def end_abs(self) -> int:
        return _abs_end(self.intervals)

    @property
    def worked_seconds(self) -> int:
        return sum(i.duration for i in self.intervals)

    def arrival_for(self, plan: PlanInput) -> int:
        """Приход к плановой смене, независимо от порядка отрезков в дейлике.

        Дополнительная работа вне смены не заменяет приход к ней. Берём начало первого
        фактического отрезка, пересекающегося с любым плановым. Если таких нет — первый
        отрезок после начала смены, иначе последний из закончившихся до неё.
        """
        if not plan.has_time:
            return self.start
        matching = [
            actual
            for actual in self.intervals
            if any(
                max(actual.start, planned.start)
                < min(actual.start + actual.duration, planned.start + planned.duration)
                for planned in plan.intervals
            )
        ]
        if matching:
            return min(i.start for i in matching)
        assert plan.start is not None
        following = [i.start for i in self.intervals if i.start >= plan.start]
        if following:
            return min(following)
        return max(self.intervals, key=lambda i: i.start + i.duration).start


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
    """Зачтённые часы, секунды; в командировке и при невыходе — 0. None — нет факта."""
    result: Seconds | None
    """Итог = Часы × e%. None — нет дейлика или не указана эффективность."""
    late: int | None
    """Опоздание либо часы подтверждённого невыхода, секунды. None — не применимо."""
    early_leave: int | None
    undertime: int | None
    planned: int | None
    no_plan: bool
    """Был дейлик, но не было плана со временем: опоздание и недоработка не считаются."""
    flags: tuple[str, ...] = field(default=())

    @property
    def is_late(self) -> bool:
        return bool(self.late)

    @property
    def arrival_start(self) -> int | None:
        """Тот же приход, по которому посчитано опоздание, для таблиц и экспорта."""
        if self.fact is None:
            return None
        if self.late is not None and self.plan is not None:
            return self.fact.arrival_for(self.plan)
        return self.fact.start


def compute_day(
    day: date,
    plan: PlanInput | None,
    fact: FactInput | None,
    status: StatusKind | None,
    rules: DayRules,
    today: date,
    *,
    confirmed_no_show_seconds: int | None = None,
) -> DayResult:
    """Посчитать день. ``today`` нужен, чтобы отличить «ещё не прислал» от «не прислал»."""
    # Явная отметка в расписании действует вместе с его версией; ручной статус приоритетнее.
    if status is None and plan is not None and plan.kind is PlanDayKind.NOTE:
        note = (plan.note or "").casefold().strip(" .!")
        status = {
            "отпуск": StatusKind.VACATION,
            "больничный": StatusKind.SICK,
            "отгул": StatusKind.DAYOFF,
        }.get(note)
    cancels = status is not None and status.cancels_plan
    holiday = day in rules.holidays
    effective_plan = None if cancels else plan
    planned_work = effective_plan is not None and effective_plan.has_time and not holiday

    excluded = status is StatusKind.BUSINESS_TRIP
    worked = (0 if excluded else fact.worked_seconds) if fact else None
    result: Seconds | None = None
    if fact is not None:
        if excluded:
            result = Fraction(0)
        elif fact.effective_seconds is not None:
            result = fact.effective_seconds

    late = early = under = None
    flags: list[str] = []
    if excluded:
        flags.append("business_trip_excluded")
    if fact is not None and planned_work and effective_plan is not None:
        assert effective_plan.start is not None
        assert effective_plan.end_abs is not None
        late = _over(fact.arrival_for(effective_plan) - effective_plan.start, rules.late_tolerance)
        early = _over(effective_plan.end_abs - fact.end_abs, rules.early_tolerance)
        planned_s = effective_plan.planned_seconds or 0
        under = _over(planned_s - fact.worked_seconds, rules.undertime_tolerance)
        for name, value in (("late", late), ("early_leave", early), ("undertime", under)):
            if value:
                flags.append(name)
    if fact is not None and fact.effective_seconds is None and not excluded:
        flags.append("no_efficiency")
    if fact is not None and any(i.crosses_midnight for i in fact.intervals):
        flags.append("overnight")
    if plan is not None and plan.kind is PlanDayKind.NOTE:
        flags.append("plan_note")

    no_plan = fact is not None and not planned_work and not cancels
    if no_plan:
        flags.append("no_plan")

    if excluded:
        state = DayState.ABSENCE
    elif fact is not None:
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

    planned = effective_plan.planned_seconds if planned_work and effective_plan else None
    if confirmed_no_show_seconds is not None:
        if confirmed_no_show_seconds <= 0:
            raise ValueError("Подтверждённый невыход должен содержать положительное время")
        if fact is not None or cancels or holiday:
            # Факт, уважительная причина или праздник требуют пересмотра решения, а не штрафа.
            flags.append("no_show_conflict")
        else:
            # Это отдельное решение админа, отсутствие дейлика само его не создаёт.
            state = DayState.ABSENCE
            worked, result = 0, Fraction(0)
            late = planned = confirmed_no_show_seconds
            early = under = None
            flags = [f for f in flags if f != "missing_daily"]
            flags.append("no_show_confirmed")

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
        planned=planned,
        no_plan=no_plan,
        flags=tuple(flags),
    )


def _over(value: int, tolerance: int) -> int:
    """Отклонение с допуском: в пределах допуска — 0, сверх допуска — целиком."""
    return value if value > tolerance else 0
