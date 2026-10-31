"""Разбор сообщения «Спринт DD.MM - DD.MM» из темы с расписанием.

Формат (см. README, раздел «Формат сообщений»):

    Спринт 26.10 - 31.10
    Иванов И.И.

    Пн: 12:00 - 18:00
    Сб: ——————
    Чт: по вайбу с 16:30 до вечера

    - задача один

    #расписание
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from enum import Enum, auto
from zoneinfo import ZoneInfo

from teamtime.parsing.text import (
    DASH_ONLY_RE,
    DATE_RE,
    TIME_MENTION_RE,
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
    Interval,
    Issue,
    MessageKind,
    ParseResult,
    PersonRef,
    PlanDay,
    PlanDayKind,
    ScheduleData,
    Severity,
)

HEADER_RE = re.compile(
    r"^спринт\s*[:#№]?\s*(?P<a>" + DATE_RE.pattern.replace("?P<", "?P<a_") + r")"
    r"\s*-+\s*(?P<b>" + DATE_RE.pattern.replace("?P<", "?P<b_") + r")",
    re.IGNORECASE,
)

_WEEKDAYS: dict[str, int] = {
    "пн": 0, "пон": 0, "понедельник": 0,
    "вт": 1, "вто": 1, "вторник": 1,
    "ср": 2, "сре": 2, "среда": 2,
    "чт": 3, "чет": 3, "четверг": 3,
    "пт": 4, "пят": 4, "пятница": 4,
    "сб": 5, "суб": 5, "суббота": 5,
    "вс": 6, "вос": 6, "воскресенье": 6,
}  # fmt: skip
WEEKDAY_SHORT = ("Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс")

DAY_RE = re.compile(
    r"^(?P<day>" + "|".join(sorted(_WEEKDAYS, key=len, reverse=True)) + r")\.?(?![а-яё])"
    r"\s*(?:[:\-]\s*)?(?P<rest>.*)$",
    re.IGNORECASE,
)

# Фамилия + инициалы: «Иванов И.И.», «Иванов И. И.», «Иванова-Петрова А.», «иванов ии».
NAME_RE = re.compile(
    r"^(?P<surname>[А-ЯЁа-яё]{2,}(?:-[А-ЯЁа-яё]{2,})?)\s+"
    r"(?P<i1>[А-ЯЁа-яё])\.?\s*(?:(?P<i2>[А-ЯЁа-яё])\.?)?$"
)
# Фамилия + имя (+ отчество) полностью: «Иванов Иван Иванович».
FULL_NAME_RE = re.compile(
    r"^(?P<surname>[А-ЯЁ][а-яё]+(?:-[А-ЯЁ][а-яё]+)?)\s+(?P<first>[А-ЯЁ][а-яё]+)"
    r"(?:\s+(?P<middle>[А-ЯЁ][а-яё]+))?$"
)

# «Задачи:», «Задачи на неделю:» — заголовок списка задач, а не непонятная строка.
TASKS_HEADER_RE = re.compile(r"^(?:задачи|tasks)(?:\s+на\s+(?:неделю|спринт))?\s*:?$")

OFF_WORDS = {"выходной", "вых", "вых.", "отдых", "отдыхаю", "нет", "не работаю", "off"}
SCHEDULE_TAGS = {"расписание", "расп", "schedule", "спринт"}


class _Section(Enum):
    HEAD = auto()
    DAYS = auto()
    TASKS = auto()


def _parse_person(line: str) -> PersonRef | None:
    if m := NAME_RE.match(line):
        initials = (m["i1"] + (m["i2"] or "")).upper()
        return PersonRef(raw=line, surname=m["surname"].capitalize(), initials=initials)
    if m := FULL_NAME_RE.match(line):
        initials = m["first"][0] + (m["middle"][0] if m["middle"] else "")
        return PersonRef(raw=line, surname=m["surname"], initials=initials.upper())
    return None


def _sprint_dates(m: re.Match[str], around: date) -> tuple[date | None, date | None]:
    def one(prefix: str, ref: date) -> date | None:
        d, mo, y = int(m[f"{prefix}_d"]), int(m[f"{prefix}_m"]), m[f"{prefix}_y"]
        if y:
            return make_date(full_year(y), mo, d)
        return closest_year(d, mo, ref)

    start = one("a", around)
    if start is None:
        return None, None
    end = one("b", start)
    if end is not None and end < start and not m["b_y"]:
        end = make_date(end.year + 1, end.month, end.day)
    return start, end


def _check_sprint_week(start: date, sent_date: date, line_no: int, raw: str) -> Issue | None:
    """Сверить неделю с датой отправки, сохранив написанные автором даты без догадок."""
    week_start = start - timedelta(days=start.weekday())
    sent_week = sent_date - timedelta(days=sent_date.weekday())
    if sent_week <= week_start <= sent_week + timedelta(days=7):
        return None
    week_end = week_start + timedelta(days=6)
    reason = (
        "эта неделя уже закончилась" if week_start < sent_week else "это позже следующей недели"
    )
    return Issue(
        "suspicious_sprint_week",
        Severity.WARNING,
        f"Сообщение отправлено {sent_date:%d.%m.%Y}, а расписание относится к неделе "
        f"{week_start:%d.%m.%Y}–{week_end:%d.%m.%Y}: {reason}",
        line_no,
        raw,
    )


def _parse_day_value(
    rest: str, line_no: int, raw: str, issues: list[Issue]
) -> tuple[PlanDayKind, tuple[Interval, ...], str | None, bool]:
    """Значение дня → (тип, интервалы, заметка, есть ли время в заметке)."""
    value = rest.strip()
    if DASH_ONLY_RE.match(value) or fold(value).strip(" .!") in OFF_WORDS:
        return PlanDayKind.OFF, (), None, False

    # Ведущий интервал (или список) и, возможно, комментарий после него.
    head, _, tail = value.partition("(")
    candidates = [(value, ""), (head, "(" + tail if tail else "")] if tail else [(value, "")]
    for times, comment in candidates:
        try:
            parsed = parse_interval_list(times)
        except TimeFormatError as exc:
            issues.append(
                Issue("bad_time", Severity.WARNING, f"Неверное время: {exc}", line_no, raw)
            )
            return PlanDayKind.NOTE, (), value, True
        if parsed:
            intervals = tuple(p.interval for p in parsed)
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
            if any(i.crosses_midnight for i in intervals):
                issues.append(
                    Issue(
                        "overnight",
                        Severity.WARNING,
                        "Интервал переходит через полночь, проверьте",
                        line_no,
                        raw,
                    )
                )
            if len(intervals) > 1:
                issues.append(
                    Issue(
                        "plan_split",
                        Severity.INFO,
                        "Несколько интервалов: план от начала первого до конца последнего",
                        line_no,
                        raw,
                    )
                )
            note = comment.strip(" ()") or None
            return PlanDayKind.WORK, intervals, note, False

    has_time = bool(TIME_MENTION_RE.search(value))
    if has_time:
        issues.append(
            Issue(
                "note_has_time",
                Severity.INFO,
                "В заметке есть время, план не задан: уточните, если нужно",
                line_no,
                raw,
            )
        )
    return PlanDayKind.NOTE, (), value, has_time


def parse_schedule(text: str, sent_at: datetime, tz: ZoneInfo) -> ParseResult:
    """Разобрать сообщение с расписанием на неделю.

    ``sent_at`` задаёт опорный год и допустимые недели: текущую и следующую.
    """
    issues: list[Issue] = []
    tags = hashtags(text)
    around = sent_at.astimezone(tz).date()

    start: date | None = None
    end: date | None = None
    person: PersonRef | None = None
    days: dict[int, tuple[str, int, str, PlanDayKind, tuple[Interval, ...], str | None, bool]] = {}
    tasks: list[str] = []
    section = _Section.HEAD
    header_seen = False
    # Продолжать предыдущую задачу можно только у пункта с «-»: строки без маркера после
    # «Задачи:» или под днём — каждая отдельная задача.
    last_bullet = False

    for line_no, raw, line in split_lines(text):
        content = strip_hashtags(line)
        if not content:
            continue

        if not header_seen and (m := HEADER_RE.match(content)):
            header_seen = True
            start, end = _sprint_dates(m, around)
            if start is None or end is None:
                issues.append(
                    Issue(
                        "bad_sprint_dates",
                        Severity.ERROR,
                        "Не удалось прочитать даты спринта",
                        line_no,
                        raw,
                    )
                )
            elif warning := _check_sprint_week(start, around, line_no, raw):
                issues.append(warning)
            continue

        if TASKS_HEADER_RE.match(fold(content)):
            section = _Section.TASKS
            last_bullet = False
            continue

        if (task := bullet_text(content)) is not None:
            section = _Section.TASKS
            tasks.append(task)
            last_bullet = True
            continue

        if m := DAY_RE.match(content):
            if section is _Section.TASKS:
                issues.append(
                    Issue(
                        "day_after_tasks",
                        Severity.INFO,
                        "Строка дня после списка задач",
                        line_no,
                        raw,
                    )
                )
            section = _Section.DAYS
            weekday = _WEEKDAYS[fold(m["day"])]
            if weekday in days:
                issues.append(
                    Issue(
                        "duplicate_day",
                        Severity.WARNING,
                        f"{WEEKDAY_SHORT[weekday]} указан повторно, взята первая строка",
                        line_no,
                        raw,
                    )
                )
                continue
            if not m["rest"].strip():
                issues.append(
                    Issue(
                        "empty_day",
                        Severity.WARNING,
                        f"{WEEKDAY_SHORT[weekday]}: нет значения, день пропущен",
                        line_no,
                        raw,
                    )
                )
                continue
            kind, intervals, note, has_time = _parse_day_value(m["rest"], line_no, raw, issues)
            days[weekday] = (raw, line_no, m["rest"], kind, intervals, note, has_time)
            continue

        if section is _Section.HEAD and person is None and (p := _parse_person(content)):
            person = p
            continue

        if section is _Section.TASKS and tasks and last_bullet:
            # Перенос длинной задачи на следующую строку.
            tasks[-1] = f"{tasks[-1]} {content}"
            continue

        if header_seen and not TIME_MENTION_RE.search(content):
            # Описание под днём, «Результат недели: …», задачи без «-» после «Задачи:».
            tasks.append(content)
            last_bullet = False
            issues.append(
                Issue(
                    "text_as_task",
                    Severity.INFO,
                    "Строка без времени записана в задачи",
                    line_no,
                    raw,
                )
            )
            continue

        issues.append(
            Issue("unknown_line", Severity.WARNING, "Непонятная строка, пропущена", line_no, raw)
        )

    if not header_seen:
        issues.append(Issue("no_header", Severity.ERROR, "Нет заголовка «Спринт ДД.ММ - ДД.ММ»"))
    if not days:
        issues.append(Issue("no_days", Severity.ERROR, "Не найдено ни одной строки с днём недели"))
    if person is None:
        issues.append(
            Issue(
                "no_person",
                Severity.WARNING,
                "Нет строки «Фамилия И.О.»: сотрудник определяется по отправителю",
            )
        )
    if start is None or end is None:
        return ParseResult(kind=MessageKind.SCHEDULE, issues=tuple(issues), hashtags=tags)

    if (end - start).days > 6:
        issues.append(
            Issue(
                "long_sprint",
                Severity.WARNING,
                "Спринт длиннее недели: план привязан к неделе даты начала",
            )
        )

    week_start = start - timedelta(days=start.weekday())
    plan_days: list[PlanDay] = []
    for weekday in sorted(days):
        raw, line_no, _rest, kind, intervals, note, has_time = days[weekday]
        day_date = week_start + timedelta(days=weekday)
        if not start <= day_date <= end:
            issues.append(
                Issue(
                    "day_outside_sprint",
                    Severity.INFO,
                    f"{WEEKDAY_SHORT[weekday]} ({day_date:%d.%m}) вне дат спринта",
                    line_no,
                    raw,
                )
            )
        plan_days.append(
            PlanDay(
                weekday=weekday,
                date=day_date,
                kind=kind,
                intervals=intervals,
                note=note,
                note_has_time=has_time,
                raw_line=raw,
                line_no=line_no,
            )
        )

    if tags and not SCHEDULE_TAGS & set(tags):
        issues.append(
            Issue(
                "tag_mismatch",
                Severity.INFO,
                f"Хэштег #{tags[0]} не похож на расписание, разобрано по содержимому",
            )
        )

    data = ScheduleData(
        sprint_start=start, sprint_end=end, person=person,
        days=tuple(plan_days), tasks=tuple(tasks),
    )  # fmt: skip
    return ParseResult(
        kind=MessageKind.SCHEDULE, issues=tuple(issues), schedule=data, hashtags=tags
    )
