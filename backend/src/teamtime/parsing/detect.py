"""Определение типа сообщения: расписание, дейлик или что-то другое."""

from __future__ import annotations

from teamtime.parsing.daily import DAILY_TAGS, DATE_LINE_RE
from teamtime.parsing.schedule import HEADER_RE, SCHEDULE_TAGS
from teamtime.parsing.text import fold, hashtags, parse_interval_list, split_lines, strip_hashtags
from teamtime.parsing.types import MessageKind


def _first_lines(text: str, limit: int = 3) -> list[str]:
    lines = [strip_hashtags(norm) for _, _, norm in split_lines(text)]
    return [line for line in lines if line][:limit]


def detect_kind(text: str, topic_hint: MessageKind | None = None) -> MessageKind:
    """Тип сообщения по содержимому, хэштегу и теме форума.

    Содержимое — самый сильный сигнал: заголовок «Спринт …» однозначен, как и пара «дата +
    интервалы» в начале. Затем хэштег, затем привязка темы. Обычная болтовня в теме даёт UNKNOWN,
    чтобы бот не реагировал на «всем привет».
    """
    head = _first_lines(text)
    if any(HEADER_RE.match(line) for line in head):
        return MessageKind.SCHEDULE
    if head and DATE_LINE_RE.match(head[0]) and any(_is_intervals(line) for line in head[1:]):
        return MessageKind.DAILY

    tags = {fold(t) for t in hashtags(text)}
    if tags & SCHEDULE_TAGS:
        return MessageKind.SCHEDULE
    if tags & DAILY_TAGS:
        return MessageKind.DAILY
    # Привязка темы сама по себе не делает реплику сообщением: нужен хотя бы намёк на формат.
    if topic_hint is MessageKind.DAILY and head and DATE_LINE_RE.match(head[0]):
        return MessageKind.DAILY
    if topic_hint is MessageKind.SCHEDULE and any(fold(line).startswith("спринт") for line in head):
        return MessageKind.SCHEDULE
    return MessageKind.UNKNOWN


def _is_intervals(line: str) -> bool:
    try:
        return bool(parse_interval_list(line))
    except ValueError:
        return True
