"""Текстовые примитивы: нормализация, время, интервалы, буллеты, хэштеги."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date

from teamtime.parsing.types import SECONDS_PER_DAY, Interval

# Все виды тире и минусов, которые встречаются в сообщениях, сводим к «-».
_DASHES = "‐‑‒–—―−﹘﹣－"
_DASH_TABLE = str.maketrans(dict.fromkeys(_DASHES, "-"))
_INVISIBLE = re.compile("[​‌‍⁠﻿­]")
_SPACES = re.compile(r"[ \t  -   　]+")


def normalize_line(line: str) -> str:
    """Строка для разбора: NFKC, единое тире, без невидимых символов, сжатые пробелы.

    Исходный текст при этом не меняется, нормализованная строка нужна только регуляркам.
    """
    line = unicodedata.normalize("NFKC", line)
    line = _INVISIBLE.sub("", line).translate(_DASH_TABLE)
    return _SPACES.sub(" ", line).strip()


def split_lines(text: str) -> list[tuple[int, str, str]]:
    """Разбить текст на строки: (номер с 1, исходная строка, нормализованная)."""
    return [
        (no, raw.rstrip(), normalize_line(raw))
        for no, raw in enumerate(text.replace("\r\n", "\n").replace("\r", "\n").split("\n"), 1)
    ]


def fold(text: str) -> str:
    """Регистр и ё/е не важны."""
    return text.casefold().replace("ё", "е")


# --- время -------------------------------------------------------------------------------

_TIME = r"(?P<{n}h>\d{{1,2}})(?:(?P<{n}sep>[:.])(?P<{n}m>\d{{2}}))?"
_INTERVAL_RE = re.compile(
    r"^(?:с\s*)?" + _TIME.format(n="a") + r"\s*(?:-+|до)\s*" + _TIME.format(n="b") + r"$",
    re.IGNORECASE,
)
TIME_MENTION_RE = re.compile(r"\b\d{1,2}[:.]\d{2}\b|\bс\s+\d{1,2}\b|\bдо\s+\d{1,2}\b", re.I)


class TimeFormatError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ParsedInterval:
    interval: Interval
    dotted: bool
    """Время записано через точку («6.00»)."""
    bare_hours: bool
    """Указаны только часы («10 - 18»)."""


def _to_seconds(hours: str, minutes: str | None, *, allow_24: bool) -> int:
    h, m = int(hours), int(minutes or 0)
    if m > 59 or h > 24 or (h == 24 and (m > 0 or not allow_24)):
        raise TimeFormatError(f"нет такого времени: {hours}:{minutes or '00'}")
    return h * 3600 + m * 60


def parse_interval(token: str) -> ParsedInterval | None:
    """«15:40 - 20:00», «6:00-14:00», «с 10:00 до 18:00» → интервал; иначе None.

    Бросает TimeFormatError, если форма интервала верная, но время невозможное (25:00).
    """
    match = _INTERVAL_RE.match(token.strip())
    if not match:
        return None
    g = match.groupdict()
    start = _to_seconds(g["ah"], g["am"], allow_24=False)
    end = _to_seconds(g["bh"], g["bm"], allow_24=True)
    if end == 0 and start > 0:
        end = SECONDS_PER_DAY  # «18:00 - 00:00» — до полуночи, а не ночная смена
    return ParsedInterval(
        interval=Interval(start, end),
        dotted="." in (g["asep"] or "", g["bsep"] or ""),
        bare_hours=g["am"] is None or g["bm"] is None,
    )


_LIST_SEP = re.compile(r"\s*[;,+&]\s*|\s+и\s+", re.IGNORECASE)


def parse_interval_list(text: str) -> list[ParsedInterval] | None:
    """Строка из одного или нескольких интервалов через «;», «,», «+», «&» или «и».

    None, если это не она.
    """
    parts = [p for p in _LIST_SEP.split(text.strip()) if p]
    if not parts:
        return None
    parsed = [parse_interval(p) for p in parts]
    if any(p is None for p in parsed):
        return None
    return [p for p in parsed if p is not None]


_TYPO_FIXES = (
    (re.compile(r"(\d{1,2})\s*:\s+(\d{2})\b|(\d{1,2})\s+:\s*(\d{2})\b"), r"\1\3:\2\4"),  # «18: 30»
    (re.compile(r"\b(\d{1,2});(\d{2})\b"), r"\1:\2"),  # «15;00»
    (re.compile(r"\b(\d{1,2}) (\d{2})\b(?!\s*[:.]\d)"), r"\1:\2"),  # «19 00»
)


def lenient_interval_list(text: str) -> tuple[list[ParsedInterval] | None, str | None]:
    """Как ``parse_interval_list``, но прощает комментарий в скобках после времени и опечатки
    в разделителе («18: 30», «15;00», «19 00»). Второе значение — что пришлось поправить:
    "comment" или "typo"; None, если строка разобралась как есть.

    Ослабления пробуются только когда строгий разбор не удался, поэтому верные строки
    читаются ровно как раньше. TimeFormatError — только из строгого разбора.
    """
    parsed = parse_interval_list(text)
    if parsed:
        return parsed, None
    head, paren, _ = text.partition("(")
    variants: list[tuple[str, str]] = []
    if paren and head.strip():
        variants.append((head, "comment"))
    for base, note in [(text, "typo"), *([(head, "typo")] if paren and head.strip() else [])]:
        fixed = base
        for pattern, repl in _TYPO_FIXES:
            fixed = pattern.sub(repl, fixed)
        if fixed != base:
            variants.append((fixed, note))
    for candidate, note in variants:
        try:
            parsed = parse_interval_list(candidate)
        except TimeFormatError:
            continue
        if parsed:
            return parsed, note
    return None, None


def format_seconds(seconds: int) -> str:
    """Время суток или длительность в «Ч:ММ» (усечение до минут)."""
    sign = "-" if seconds < 0 else ""
    seconds = abs(seconds)
    return f"{sign}{seconds // 3600}:{seconds % 3600 // 60:02d}"


# --- даты --------------------------------------------------------------------------------

DATE_RE = re.compile(r"(?P<d>\d{1,2})[./](?P<m>\d{1,2})(?:[./](?P<y>\d{4}|\d{2}))?")


def make_date(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def full_year(y: str) -> int:
    return int(y) + 2000 if len(y) == 2 else int(y)


def closest_year(day: int, month: int, around: date) -> date | None:
    """Дата с днём и месяцем, ближайшая к ``around`` (год ±1). Учитывает переход через Новый год."""
    candidates = [make_date(around.year + d, month, day) for d in (-1, 0, 1)]
    valid = [c for c in candidates if c is not None]
    if not valid:
        return None
    return min(valid, key=lambda c: abs((c - around).days))


# --- структура сообщения -------------------------------------------------------------------

BULLET_RE = re.compile(r"^(?:[-*•·▪◦‣>]+|\d{1,2}[.)])\s*(?P<text>.+)$")
DASH_ONLY_RE = re.compile(r"^[-_=~.\s]+$")
HASHTAG_RE = re.compile(r"#([\wё]+)", re.IGNORECASE)


def bullet_text(line: str) -> str | None:
    """Текст буллета или None. Строка из одних прочерков буллетом не считается."""
    if DASH_ONLY_RE.match(line):
        return None
    match = BULLET_RE.match(line)
    if not match:
        return None
    text = match.group("text").strip()
    # «- 10:00 - 18:00» скорее строка времени, чем задача, но решать это вызывающему.
    return text or None


def hashtags(text: str) -> tuple[str, ...]:
    return tuple(dict.fromkeys(fold(t) for t in HASHTAG_RE.findall(text)))


def strip_hashtags(line: str) -> str:
    return HASHTAG_RE.sub("", line).strip()
