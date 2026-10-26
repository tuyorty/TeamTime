"""Типы результата разбора. Все неизменяемые, без зависимостей от БД."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from enum import StrEnum

SECONDS_PER_DAY = 24 * 60 * 60


class MessageKind(StrEnum):
    SCHEDULE = "schedule"
    DAILY = "daily"
    UNKNOWN = "unknown"


class ParseStatus(StrEnum):
    OK = "ok"
    PARTIAL = "partial"
    FAILED = "failed"


class Severity(StrEnum):
    INFO = "info"
    """Замечание: статус не портит, но может подсвечиваться в UI."""
    WARNING = "warning"
    """Часть сообщения не разобрана или неоднозначна: статус partial."""
    ERROR = "error"
    """Сообщение нельзя использовать: статус failed."""


class PlanDayKind(StrEnum):
    WORK = "work"
    """Есть плановое время."""
    OFF = "off"
    """Явный выходной (прочерк)."""
    NOTE = "note"
    """Свободный текст без плана по времени («по вайбу»)."""


@dataclass(frozen=True, slots=True)
class Issue:
    code: str
    severity: Severity
    message: str
    line_no: int | None = None
    """Номер строки в исходном тексте, с 1."""
    line: str | None = None


@dataclass(frozen=True, slots=True)
class Interval:
    """Интервал времени в секундах от полуночи. ``end`` может быть меньше ``start``,
    тогда интервал переходит через полночь."""

    start: int
    end: int

    @property
    def crosses_midnight(self) -> bool:
        return self.end < self.start

    @property
    def duration(self) -> int:
        if self.crosses_midnight:
            return SECONDS_PER_DAY - self.start + self.end
        return self.end - self.start


@dataclass(frozen=True, slots=True)
class PersonRef:
    """Строка «Иванов И.И.» из расписания."""

    raw: str
    surname: str
    initials: str
    """Инициалы без точек и пробелов: «ИИ»."""

    @property
    def key(self) -> str:
        return person_key(self.surname, self.initials)


def _fold(text: str) -> str:
    return text.lower().replace("ё", "е").replace(".", "").replace(" ", "")


def person_key(surname: str, initials: str) -> str:
    """Ключ сопоставления: регистр и ё/е не важны, точки и пробелы убраны."""
    return f"{_fold(surname)} {_fold(initials)}".strip()


@dataclass(frozen=True, slots=True)
class PlanDay:
    weekday: int
    """0 — понедельник, 6 — воскресенье."""
    date: date
    kind: PlanDayKind
    intervals: tuple[Interval, ...] = ()
    note: str | None = None
    note_has_time: bool = False
    raw_line: str = ""
    line_no: int = 0

    @property
    def start(self) -> int | None:
        return self.intervals[0].start if self.intervals else None

    @property
    def end(self) -> int | None:
        return self.intervals[-1].end if self.intervals else None

    @property
    def planned_seconds(self) -> int | None:
        return sum(i.duration for i in self.intervals) if self.intervals else None


@dataclass(frozen=True, slots=True)
class ScheduleData:
    sprint_start: date
    sprint_end: date
    person: PersonRef | None
    days: tuple[PlanDay, ...]
    tasks: tuple[str, ...]

    @property
    def iso_year(self) -> int:
        return self.sprint_start.isocalendar().year

    @property
    def iso_week(self) -> int:
        return self.sprint_start.isocalendar().week

    @property
    def week_start(self) -> date:
        return self.sprint_start - timedelta(days=self.sprint_start.weekday())


@dataclass(frozen=True, slots=True)
class DailyData:
    work_date: date
    intervals: tuple[Interval, ...]
    efficiency: int | None
    tasks: tuple[str, ...]

    @property
    def worked_seconds(self) -> int:
        return sum(i.duration for i in self.intervals)

    @property
    def start(self) -> int:
        return self.intervals[0].start

    @property
    def end(self) -> int:
        return self.intervals[-1].end


@dataclass(frozen=True, slots=True)
class ParseResult:
    kind: MessageKind
    issues: tuple[Issue, ...] = ()
    schedule: ScheduleData | None = None
    daily: DailyData | None = None
    hashtags: tuple[str, ...] = field(default=())

    @property
    def status(self) -> ParseStatus:
        severities = {i.severity for i in self.issues}
        if Severity.ERROR in severities or (self.schedule is None and self.daily is None):
            return ParseStatus.FAILED
        if Severity.WARNING in severities:
            return ParseStatus.PARTIAL
        return ParseStatus.OK

    @property
    def warnings(self) -> tuple[Issue, ...]:
        return tuple(i for i in self.issues if i.severity is not Severity.INFO)
