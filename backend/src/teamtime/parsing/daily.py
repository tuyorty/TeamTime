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
from difflib import SequenceMatcher
from zoneinfo import ZoneInfo

from teamtime.parsing.text import (
    DATE_RE,
    TimeFormatError,
    bullet_text,
    closest_year,
    fold,
    format_seconds,
    full_year,
    hashtags,
    lenient_interval_list,
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
# «Эффективность: 70%», «эффективность 70», «Эфф. — 70 %», «Эфективность:70»,
# «Эффективность: 90% (сидел с кнопкой)» — комментарий в скобках после процента не мешает.
EFFICIENCY_RE = re.compile(
    r"^(?P<word>[а-яa-z]+%?)\.?\s*[:=\-]?\s*(?P<value>\d+(?:[.,]\d+)?)\s*%?\s*(?P<comment>\(.*)?$"
)
EFFICIENCY_WORD_RE = re.compile(r"^(?P<word>[а-яa-z]+%?)")
EFFICIENCY_WORD = "эффективность"
DAILY_TAGS = {"дейли", "дейлик", "дейлики", "daily", "дэйли", "отчет"}

MAX_BACKDATE_DAYS = 31


def _efficiency_word(word: str) -> bool:
    """«эффективность» с опечатками («эффеткивность», «эфективонсть»), «эфф», «кпд», «e%»."""
    word = word.rstrip("%")
    if word in {"кпд", "e", "е"}:
        return True
    if len(word) >= 2 and (EFFICIENCY_WORD.startswith(word) or "эфективность".startswith(word)):
        return True  # сокращение: «эф», «эфф», «эффект»
    return word.startswith("эф") and SequenceMatcher(None, word, EFFICIENCY_WORD).ratio() >= 0.8


def _fix_year(work_date: date, sent: date) -> date | None:
    """Год с опечаткой («27.10.2025», отправлено 27.10.2026): тот же день и месяц в году
    отправки, если так дата попадает в обычное окно «за последний месяц»."""
    guess = closest_year(work_date.day, work_date.month, sent)
    if guess is None or guess.year == work_date.year:
        return None
    return guess if 0 <= (sent - guess).days <= MAX_BACKDATE_DAYS else None


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
    # Шапка (дата, время, эффективность) закончилась: дальше свободный текст — это пункты.
    header_done = False
    # Пустая строка рвёт продолжение пункта: следующий текст без «-» — новый пункт.
    after_blank = False
    after_tag = False

    for line_no, raw, line in split_lines(text):
        content = strip_hashtags(line)
        if not content:
            if line and DAILY_TAGS & {fold(t) for t in hashtags(line)} and tasks:
                after_tag = True  # строка «#дейли» закрывает дейлик
            if not line and intervals:
                header_done = True
            after_blank = True
            continue
        if after_tag:
            issues.append(
                Issue(
                    "text_after_tag",
                    Severity.INFO,
                    "Текст после хэштега дейлика не учтён",
                    line_no,
                    raw,
                )
            )
            break
        was_blank, after_blank = after_blank, False

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
                if work_date is not None and (fixed := _fix_year(work_date, sent_local)):
                    issues.append(
                        Issue(
                            "year_fixed",
                            Severity.INFO,
                            f"Год {work_date.year} похож на опечатку: дейлик отнесён "
                            f"к {fixed:%d.%m.%Y}",
                            line_no,
                            raw,
                        )
                    )
                    work_date = fixed
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

        if (m := EFFICIENCY_RE.match(folded)) and _efficiency_word(m["word"]):
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
                if m["comment"]:
                    issues.append(
                        Issue(
                            "comment_ignored",
                            Severity.INFO,
                            "Комментарий в скобках не учтён",
                            line_no,
                            raw,
                        )
                    )
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
            if intervals:
                header_done = True
            continue

        if not in_tasks:
            try:
                parsed, relaxed = lenient_interval_list(content)
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
                if relaxed == "comment":
                    issues.append(
                        Issue(
                            "comment_ignored",
                            Severity.INFO,
                            "Комментарий в скобках не учтён",
                            line_no,
                            raw,
                        )
                    )
                elif relaxed == "typo":
                    issues.append(
                        Issue(
                            "time_typo",
                            Severity.INFO,
                            "Опечатка во времени исправлена: "
                            + "; ".join(
                                f"{format_seconds(p.interval.start)} - "
                                f"{format_seconds(p.interval.end)}"
                                for p in parsed
                            ),
                            line_no,
                            raw,
                        )
                    )
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

        if (w := EFFICIENCY_WORD_RE.match(folded)) and _efficiency_word(w["word"]):
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

        if in_tasks and tasks and not was_blank:
            tasks[-1] = f"{tasks[-1]} {content}"
            continue

        if header_done and work_date is not None:
            in_tasks = True
            tasks.append(content)
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
