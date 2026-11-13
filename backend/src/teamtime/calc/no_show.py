"""Проверка границ смены перед подтверждением невыхода; обычные расчёты не меняются."""

from teamtime.calc.day import PlanInput
from teamtime.parsing.types import SECONDS_PER_DAY


def confirmed_shift_end(plan: PlanInput | None) -> int | None:
    """Конец однозначной смены без пересечений, в секундах от полуночи её даты.

    После явного перехода через полночь следующие утренние интервалы относятся к новым
    суткам: «22–02; 03–05» заканчивается в 29:00. Обратный порядок до перехода через полночь
    нельзя отличить от ошибки ввода, поэтому такой план сначала исправляет администратор.
    """
    if plan is None or not plan.has_time:
        return None
    offset = 0
    previous_end: int | None = None
    for interval in plan.intervals:
        if not (0 <= interval.start < SECONDS_PER_DAY and 0 <= interval.end <= SECONDS_PER_DAY):
            return None
        start = interval.start + offset
        if (
            previous_end is not None
            and start < previous_end
            and offset == 0
            and previous_end >= SECONDS_PER_DAY
        ):
            offset = SECONDS_PER_DAY
            start += offset
        if (
            interval.duration <= 0
            or (previous_end is not None and start < previous_end)
            or (offset and interval.crosses_midnight)
        ):
            return None
        previous_end = start + interval.duration
    return previous_end
