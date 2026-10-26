"""Детерминированный разбор сообщений. Чистые функции: текст → результат + предупреждения.

Модуль не знает о базе, сети и текущем времени. Всё внешнее (дата отправки, часовой пояс,
подсказка темы) приходит аргументами.
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from teamtime.parsing.daily import parse_daily
from teamtime.parsing.detect import detect_kind
from teamtime.parsing.schedule import parse_schedule
from teamtime.parsing.types import (
    DailyData,
    Interval,
    Issue,
    MessageKind,
    ParseResult,
    ParseStatus,
    PersonRef,
    PlanDay,
    PlanDayKind,
    ScheduleData,
    Severity,
    person_key,
)

PARSER_VERSION = 1
"""Увеличивается при изменении правил разбора: по нему можно найти и переразобрать сообщения."""

__all__ = [
    "PARSER_VERSION",
    "DailyData",
    "Interval",
    "Issue",
    "MessageKind",
    "ParseResult",
    "ParseStatus",
    "PersonRef",
    "PlanDay",
    "PlanDayKind",
    "ScheduleData",
    "Severity",
    "detect_kind",
    "parse_daily",
    "parse_message",
    "parse_schedule",
    "person_key",
]


def parse_message(
    text: str,
    sent_at: datetime,
    tz: ZoneInfo,
    topic_hint: MessageKind | None = None,
) -> ParseResult:
    """Определить тип и разобрать. Для UNKNOWN возвращает пустой результат без проблем."""
    kind = detect_kind(text, topic_hint)
    if kind is MessageKind.SCHEDULE:
        result = parse_schedule(text, sent_at, tz)
    elif kind is MessageKind.DAILY:
        result = parse_daily(text, sent_at, tz)
    else:
        return ParseResult(kind=MessageKind.UNKNOWN)
    if topic_hint is not None and topic_hint is not kind:
        mismatch = Issue(
            "topic_mismatch",
            Severity.INFO,
            "Сообщение отправлено не в ту тему, разобрано по содержимому",
        )
        result = ParseResult(
            kind=result.kind,
            issues=(*result.issues, mismatch),
            schedule=result.schedule,
            daily=result.daily,
            hashtags=result.hashtags,
        )
    return result
