"""Расчёты таблицы. Чистые функции в точных секундах (``fractions.Fraction``).

Показ «Ч:ММ» усекает вниз до минут, как исходная Google-таблица, поэтому числа совпадают с ней.
"""

from teamtime.calc.day import (
    STATUS_LABELS,
    DayResult,
    DayRules,
    DayState,
    FactInput,
    PlanInput,
    StatusKind,
    compute_day,
)
from teamtime.calc.duration import format_hm, format_hms, hm, parse_hm
from teamtime.calc.month import MonthSummary, overtime_bonus, summarize_month
from teamtime.calc.penalty import DEFAULT_SCALE, PenaltyScale

__all__ = [
    "DEFAULT_SCALE",
    "STATUS_LABELS",
    "DayResult",
    "DayRules",
    "DayState",
    "FactInput",
    "MonthSummary",
    "PenaltyScale",
    "PlanInput",
    "StatusKind",
    "compute_day",
    "format_hm",
    "format_hms",
    "hm",
    "overtime_bonus",
    "parse_hm",
    "summarize_month",
]
