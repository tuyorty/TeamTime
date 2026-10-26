"""Разбор дейлика из темы «дейлики».

Формат (см. README, раздел «Формат сообщений»):

    22.10.2026
    13:30 - 15:30; 17:30 - 18:40
    Эффективность: 100%

    - фиксы безопасности

    #дейли

Дата в первой строке — дата рабочего дня, а не отправки: дейлик за 22.10 могут прислать 24.10.
"""

from __future__ import annotations

import itertools
import re
from datetime import date, datetime
from zoneinfo import ZoneInfo

from teamtime.parsing.text import (
    DATE_RE,
    TimeFormatError,
    bullet_text,
    closest_year,
    fold,
    full_year,
    hashtags,
    make_date,
    parse_interval_list,
    split_lines,
    strip_hashtags,
)
from teamtime.parsing.types import (
    DailyData,
    Interval,
    Issue,
    MessageKind,
    ParseResult,
    Severity,
)

DATE_LINE_RE = re.compile(r"^(?:дата\s*:?\s*)?" + DATE_RE.pattern + r"(?P<tail>.*)$", re.I)
# «Эффективность: 70%», «эффективность 70», «Эфф. — 70 %», «Эфективность:70».
EFFICIENCY_RE = re.compile(
    r"^(?:эф+е?к?т?и?в?н?о?с?т?ь?|кпд|[eе]%?)\.?\s*[:=\-]?\s*(?P<value>\d{1,3}(?:[.,]\d+)?)\s*%?\s*$"
)
EFFICIENCY_WORD_RE = re.compile(r"^(?:эф|кпд)")
DAILY_TAGS = {"дейли", "дейлик", "дейлики", "daily", "дэйли", "отчет"}

MAX_BACKDATE_DAYS = 31


def _overlaps(intervals: list[Interval]) -> bool:
    spans = sorted((i.start, i.start + i.duration) for i in intervals)
    return any(prev_end > start for (_, prev_end), (start, _) in itertools.pairwise(spans))


def _looks_like_intervals(line: str) -> bool:
    """«15.40 - 20.00» похоже на дату, но это интервал."""
    try:
        return bool(parse_interval_list(line))
    except TimeFormatError:
        return True


def parse_daily(text: str, sent_at: datetime, tz: ZoneInfo) -> ParseResult:
    """Разобрать дейлик. ``sent_at`` нужен для проверки даты и года, если он не указан."""
    issues: list[Issue] = []
    tags = hashtags(text)
    sent_local = sent_at.astimezone(tz).date()

    work_date: date | None = None
    intervals: list[Interval] = []
    efficiency: int | None = None
    tasks: list[str] = []
    in_tasks = False

    for line_no, raw, line in split_lines(text):
        content = strip_hashtags(line)
        if not content:
            continue

        folded = fold(content)
        if (
            work_date is None
            and not intervals
            and not _looks_like_intervals(content)
            and (m := DATE_LINE_RE.match(content))
        ):
            day, month = int(m["d"]), int(m["m"])
            if m["y"]:
                work_date = make_date(full_year(m["y"]), month, day)
            else:
                work_date = closest_year(day, month, sent_local)
                issues.append(
                    Issue(
                        "year_inferred",
                        Severity.INFO,
                        "Год не указан, взят по дате отправки",
                        line_no,
                        raw,
                    )
                )
            if work_date is None:
                issues.append(Issue("bad_date", Severity.ERROR, "Нет такой даты", line_no, raw))
            tail = m["tail"].strip(" ,()-")
            # Хвост «(пт)» или «пятница» нормален, а вот время на той же строке — разберём.
            if tail:
                try:
                    parsed = parse_interval_list(tail)
                except TimeFormatError:
                    parsed = None
                if parsed:
                    intervals.extend(p.interval for p in parsed)
            continue

        if m := EFFICIENCY_RE.match(folded):
            value = float(m["value"].replace(",", "."))
            if efficiency is not None:
                issues.append(
                    Issue(
                        "duplicate_efficiency",
                        Severity.WARNING,
                        "Эффективность указана дважды, взята первая",
                        line_no,
                        raw,
                    )
                )
            elif not 0 <= value <= 100:
                issues.append(
                    Issue(
                        "bad_efficiency",
                        Severity.WARNING,
                        "Эффективность должна быть от 0 до 100%",
                        line_no,
                        raw,
                    )
                )
            else:
                if value != int(value):
                    issues.append(
                        Issue(
                            "fractional_efficiency",
                            Severity.INFO,
                            "Дробная эффективность округлена до целого",
                            line_no,
                            raw,
                        )
                    )
                efficiency = round(value)
            continue

        if not in_tasks:
            try:
                parsed = parse_interval_list(content)
            except TimeFormatError as exc:
                issues.append(
                    Issue("bad_time", Severity.ERROR, f"Неверное время: {exc}", line_no, raw)
                )
                continue
            if parsed:
                if intervals:
                    issues.append(
                        Issue(
                            "intervals_multiline",
                            Severity.INFO,
                            "Интервалы на нескольких строках объединены",
                            line_no,
                            raw,
                        )
                    )
                intervals.extend(p.interval for p in parsed)
                if any(p.dotted for p in parsed):
                    issues.append(
                        Issue(
                            "dotted_time",
                            Severity.INFO,
                            "Время через точку понято как «Ч:ММ»",
                            line_no,
                            raw,
                        )
                    )
                if any(p.bare_hours for p in parsed):
                    issues.append(
                        Issue(
                            "bare_hours",
                            Severity.INFO,
                            "Время без минут понято как «Ч:00»",
                            line_no,
                            raw,
                        )
                    )
                continue

        if (task := bullet_text(content)) is not None:
            in_tasks = True
            tasks.append(task)
            continue

        if EFFICIENCY_WORD_RE.match(folded):
            issues.append(
                Issue(
                    "bad_efficiency",
                    Severity.WARNING,
                    "Не удалось прочитать эффективность",
                    line_no,
                    raw,
                )
            )
            continue

        if in_tasks and tasks:
            tasks[-1] = f"{tasks[-1]} {content}"
            continue

        issues.append(
            Issue("unknown_line", Severity.WARNING, "Непонятная строка, пропущена", line_no, raw)
        )

    if work_date is None and not any(i.code == "bad_date" for i in issues):
        issues.append(
            Issue("no_date", Severity.ERROR, "Нет даты рабочего дня в формате ДД.ММ.ГГГГ")
        )
    if not intervals:
        issues.append(
            Issue(
                "no_intervals", Severity.ERROR, "Нет интервалов времени, например «10:00 - 18:00»"
            )
        )
    if efficiency is None and not any(i.code == "bad_efficiency" for i in issues):
        issues.append(
            Issue(
                "no_efficiency",
                Severity.WARNING,
                "Нет строки «Эффективность: N%»: итог за день не посчитан",
            )
        )

    if any(i.crosses_midnight for i in intervals):
        issues.append(
            Issue(
                "overnight",
                Severity.WARNING,
                "Интервал переходит через полночь: часы отнесены к дате дейлика",
            )
        )
    if any(i.duration == 0 for i in intervals):
        issues.append(Issue("empty_interval", Severity.WARNING, "Интервал нулевой длины"))
    if _overlaps(intervals):
        issues.append(Issue("overlap", Severity.WARNING, "Интервалы пересекаются"))

    if work_date is not None:
        delta = (sent_local - work_date).days
        if delta < 0:
            issues.append(
                Issue("future_date", Severity.WARNING, "Дата дейлика позже даты отправки")
            )
        elif delta > MAX_BACKDATE_DAYS:
            issues.append(
                Issue(
                    "old_date",
                    Severity.WARNING,
                    f"Дейлик прислан через {delta} дн. после рабочего дня, проверьте дату",
                )
            )

    if tags and not DAILY_TAGS & {fold(t) for t in tags}:
        issues.append(
            Issue(
                "tag_mismatch",
                Severity.INFO,
                f"Хэштег #{tags[0]} не похож на дейлик, разобрано по содержимому",
            )
        )

    if work_date is None or not intervals:
        return ParseResult(kind=MessageKind.DAILY, issues=tuple(issues), hashtags=tags)

    data = DailyData(
        work_date=work_date, intervals=tuple(intervals), efficiency=efficiency, tasks=tuple(tasks)
    )
    return ParseResult(kind=MessageKind.DAILY, issues=tuple(issues), daily=data, hashtags=tags)
