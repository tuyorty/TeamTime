"""DTO для API и отчётов. Длительности — целые секунды (усечены), время суток — секунды от полуночи.

Фронтенд ничего не пересчитывает: все итоги приходят готовыми, клиент их только форматирует.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from teamtime.calc import DayState, StatusKind
from teamtime.db.models import Resolution, Source, TopicKind
from teamtime.parsing import MessageKind, ParseStatus, PlanDayKind


class Schema(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --- справочники ---------------------------------------------------------------------------


class EmployeeBrief(Schema):
    id: int
    short_name: str = Field(description="«Иванов И.И.»")
    full_name: str
    position: str
    color: str
    is_active: bool
    avatar_url: str = ""


class EmployeeOut(EmployeeBrief):
    monthly_norm_minutes: int
    hourly_rate: Decimal
    match_key: str
    phone: str
    about: str


class EmployeeIn(BaseModel):
    full_name: str = Field(min_length=3, max_length=200)
    short_name: str = Field(
        min_length=3, max_length=100, description="Как в расписании: «Иванов И.И.»"
    )
    position: str = Field("", max_length=200)
    phone: str = Field("", max_length=40, pattern=r"^[+\d\s().-]*$")
    about: str = Field("", max_length=500)
    avatar_url: str = Field(
        "",
        max_length=200_000,
        pattern=r"^(data:image/(?:png|jpeg|webp);base64,[A-Za-z0-9+/=]+)?$",
    )
    monthly_norm_minutes: int = Field(160 * 60, ge=0, le=400 * 60)
    hourly_rate: Decimal = Field(Decimal(0), ge=0, le=Decimal(1_000_000))
    color: str = Field("", max_length=16)
    is_active: bool = True


class IdentityOut(Schema):
    id: int
    telegram_user_id: int
    username: str | None
    display_name: str
    employee: EmployeeBrief | None
    suggested_employee: EmployeeBrief | None
    linked_at: datetime | None
    last_seen_at: datetime


class TopicOut(Schema):
    id: int
    chat_id: int
    thread_id: int | None
    kind: TopicKind
    title: str
    chat_title: str = ""


class ChatOut(Schema):
    chat_id: int
    title: str
    is_forum: bool
    approved: bool
    topics: int = 0


class ChatIn(BaseModel):
    approved: bool


class TopicIn(BaseModel):
    chat_id: int
    thread_id: int | None = None
    kind: TopicKind
    title: str = ""


# --- ячейка дня ----------------------------------------------------------------------------


class PlanOut(BaseModel):
    kind: PlanDayKind
    start: int | None
    end: int | None
    planned_sec: int | None
    intervals: list[tuple[int, int]]
    note: str | None
    note_has_time: bool
    raw_line: str


class FactOut(BaseModel):
    start: int
    end: int
    intervals: list[tuple[int, int]]
    worked_sec: int
    efficiency: int | None
    result_sec: int | None
    tasks: list[str]
    edited: bool
    sent_at: datetime | None
    source: Source


class SourceRef(BaseModel):
    plan_id: int | None = None
    plan_version: int | None = None
    plan_message_version_id: int | None = None
    daily_id: int | None = None
    daily_version: int | None = None
    daily_message_version_id: int | None = None
    plan_raw_message_id: int | None = None
    daily_raw_message_id: int | None = None


class DayCellOut(BaseModel):
    date: date
    state: DayState
    status: StatusKind | None
    status_label: str | None
    status_note: str | None
    plan: PlanOut | None
    fact: FactOut | None
    late_sec: int | None = Field(description="Опоздание; None — не применимо (нет плана/факта)")
    early_leave_sec: int | None
    undertime_sec: int | None
    no_plan: bool
    flags: list[str]
    source: SourceRef


# --- неделя --------------------------------------------------------------------------------


class Totals(BaseModel):
    worked_sec: int = 0
    result_sec: int = 0
    planned_sec: int = 0
    late_sec: int = 0
    late_count: int = 0
    early_count: int = 0
    undertime_count: int = 0
    days_worked: int = 0
    days_missing: int = 0
    days_no_plan: int = 0


class WeekPlanInfo(BaseModel):
    plan_id: int
    version: int
    versions: int
    edited: bool
    tasks: list[str]
    sprint_start: date
    sprint_end: date


class WeekRow(BaseModel):
    employee: EmployeeBrief
    cells: list[DayCellOut]
    totals: Totals
    plan: WeekPlanInfo | None


class DayTotals(BaseModel):
    date: date
    worked_sec: int
    planned_count: int
    worked_count: int
    late_count: int
    missing_count: int
    absence_count: int


class WeekOut(BaseModel):
    iso_year: int
    iso_week: int
    label: str = Field(description="«44 неделя»")
    week_start: date
    days: list[date]
    rows: list[WeekRow]
    day_totals: list[DayTotals]
    totals: Totals
    today: date
    highlights: PeriodHighlights = Field(default_factory=lambda: PeriodHighlights())


# --- месяц ---------------------------------------------------------------------------------


class MonthSummaryOut(BaseModel):
    worked_sec: int = Field(description="Часы(+)")
    result_sec: int = Field(description="Часы(e%)")
    late_total_sec: int = Field(description="Сумма опозданий")
    late_count: int
    penalty_sec: int = Field(description="Опоздания(−): штраф по шкале")
    total_sec: int = Field(description="Итого = Часы(e%) − Опоздания(−)")
    norm_sec: int
    norm_progress: float
    overtime_sec: int
    bonus: Decimal = Field(description="Премия за переработку, ₽")
    hourly_rate: Decimal
    days_worked: int
    days_missing: int
    days_no_plan: int
    days_without_efficiency: int
    statuses: dict[str, int]


class LateDay(BaseModel):
    date: date
    late_sec: int
    plan_start: int
    fact_start: int


class WeekPoint(BaseModel):
    iso_week: int
    label: str
    worked_sec: int
    result_sec: int
    late_sec: int


class MonthRow(BaseModel):
    employee: EmployeeOut
    summary: MonthSummaryOut
    late_days: list[LateDay]
    weeks: list[WeekPoint]


class PenaltyScaleOut(BaseModel):
    soft_limit_h: float
    hard_limit_h: float
    quad_coef: float
    hard_value_h: float
    tail_slope: float
    problems: list[str]


class MonthHistoryPoint(BaseModel):
    year: int
    month: int
    label: str
    worked_sec: int
    result_sec: int
    total_sec: int
    penalty_sec: int
    norm_sec: int


class Deviation(BaseModel):
    employee: EmployeeBrief
    date: date
    kind: Literal["late", "early_leave", "undertime", "missing_daily", "no_plan"]
    value_sec: int | None


class MonthOut(BaseModel):
    year: int
    month: int
    label: str
    first_day: date
    last_day: date
    rows: list[MonthRow]
    scale: PenaltyScaleOut
    history: list[MonthHistoryPoint]
    deviations: list[Deviation]
    complete: bool = Field(description="Месяц закончился (иначе итоги промежуточные)")
    highlights: PeriodHighlights = Field(default_factory=lambda: PeriodHighlights())


class HighlightOccurrence(BaseModel):
    date: date
    employee: EmployeeBrief | None = None
    participants: int | None = None


class HighlightRecord(BaseModel):
    value_sec: int
    occurrences: list[HighlightOccurrence]
    total_occurrences: int


class PeriodHighlights(BaseModel):
    reported_days: int = 0
    employees_reported: int = 0
    worked_sec: int = 0
    tasks_reported: int = 0
    average_day_sec: int | None = None
    comparable_days: int = 0
    on_time_days: int = 0
    missing_days: int = 0
    earliest_start: HighlightRecord | None = None
    latest_finish: HighlightRecord | None = None
    longest_day: HighlightRecord | None = None
    largest_lateness: HighlightRecord | None = None
    busiest_day: HighlightRecord | None = None


# --- сегодня -------------------------------------------------------------------------------


class TodayRow(BaseModel):
    employee: EmployeeBrief
    cell: DayCellOut
    presence: Literal["on_site", "expected_later", "left", "no_plan", "absent", "remote", "off"]
    daily_overdue: bool = Field(description="План закончился, а дейлика нет")
    tasks: list[str] = Field(default_factory=list, description="Задачи из расписания на неделю")


class FeedItem(BaseModel):
    id: int
    at: datetime
    kind: MessageKind
    status: ParseStatus
    resolution: Resolution
    employee: EmployeeBrief | None
    author_name: str
    summary: str
    edited: bool
    raw_message_id: int


class TodayOut(BaseModel):
    date: date
    now_sec: int
    rows: list[TodayRow]
    counts: dict[str, int]
    worked_sec: int
    feed: list[FeedItem]
    week_pulse: list[DayTotals]


# --- сотрудник -----------------------------------------------------------------------------


class Streaks(BaseModel):
    current_on_time: int = Field(description="Дней подряд без опозданий (с дейликом)")
    best_on_time: int
    current_dailies: int = Field(description="Рабочих дней подряд с дейликом")


class WeekTasks(BaseModel):
    iso_year: int
    iso_week: int
    label: str
    planned: list[str]
    done: list[tuple[date, list[str]]]


class NoteItem(BaseModel):
    date: date
    kind: Literal["plan_note", "status"]
    text: str
    status: StatusKind | None = None


class EmployeeDetailOut(BaseModel):
    employee: EmployeeOut
    identities: list[IdentityOut]
    start: date
    end: date
    days: list[DayCellOut]
    totals: Totals
    avg_start_sec: int | None
    arrivals: list[int] = Field(description="Время прихода по дням с фактом, секунды")
    late_minutes: list[int] = Field(description="Отклонение прихода от плана, минуты (+ опоздание)")
    streaks: Streaks
    weeks: list[WeekPoint]
    tasks: list[WeekTasks]
    notes: list[NoteItem]
    month: MonthSummaryOut


# --- планы ---------------------------------------------------------------------------------


class PlanVersionOut(BaseModel):
    id: int
    version: int
    created_at: datetime
    source: Source
    created_by: str
    edited: bool
    retracted: bool
    days: list[tuple[date, PlanOut]]
    tasks: list[str]
    message_version_id: int | None
    raw_message_id: int | None


class PlanRow(BaseModel):
    employee: EmployeeBrief
    current: PlanVersionOut | None
    versions: list[PlanVersionOut]
    done_tasks: list[str]
    days_with_daily: int
    days_planned: int


class PlansOut(BaseModel):
    iso_year: int
    iso_week: int
    label: str
    week_start: date
    days: list[date]
    rows: list[PlanRow]


# --- сообщения и инбокс --------------------------------------------------------------------


class IssueOut(BaseModel):
    code: str
    severity: str
    message: str
    line_no: int | None = None
    line: str | None = None


class MessageVersionOut(Schema):
    id: int
    version: int
    text: str
    edited_at: datetime | None
    received_at: datetime


class ParseResultOut(BaseModel):
    id: int
    message_version_id: int
    version: int
    parser_version: int
    kind: MessageKind
    status: ParseStatus
    resolution: Resolution
    issues: list[IssueOut]
    data: dict[str, Any] | None
    employee: EmployeeBrief | None
    employee_unresolved: bool
    created_at: datetime
    is_latest: bool


class MessageOut(BaseModel):
    id: int
    chat_id: int
    message_id: int
    thread_id: int | None
    author_name: str
    author_tg_id: int | None
    sent_at: datetime
    source: Source
    versions: list[MessageVersionOut]
    parses: list[ParseResultOut]
    telegram_link: str | None


class InboxItem(BaseModel):
    parse: ParseResultOut
    message: MessageOut
    candidates: list[EmployeeBrief]
    plan_change: ScheduleChangePreview | None = None


class ScheduleDayChange(BaseModel):
    date: date
    previous: PlanOut | None
    submitted: PlanOut | None
    current: DayCellOut
    if_accepted: DayCellOut
    affects_calculation: bool


class ScheduleChangePreview(BaseModel):
    plan_id: int
    version: int
    previous_version: int | None
    late_change: bool
    days: list[ScheduleDayChange]
    tasks_added: list[str]
    tasks_removed: list[str]


class InboxOut(BaseModel):
    items: list[InboxItem]
    counts: dict[str, int]
    total: int = 0
    """Сколько записей подходит под фильтры (в items — не больше лимита)."""


# --- поиск ---------------------------------------------------------------------------------


class SearchHit(BaseModel):
    kind: Literal["employee", "day", "task", "page"]
    title: str
    subtitle: str
    href: str


class SearchOut(BaseModel):
    query: str
    hits: list[SearchHit]


# --- аудит ---------------------------------------------------------------------------------


class AuditOut(Schema):
    id: int
    at: datetime
    actor: str
    action: str
    entity_type: str
    entity_id: str
    employee_id: int | None
    before: dict[str, Any] | None
    after: dict[str, Any] | None
    reason: str


class MetaOut(BaseModel):
    version: str
    demo: bool
    admin_enabled: bool
    is_admin: bool
    timezone: str
    today: date
    now: datetime
    bot_username: str | None
    late_tolerance_min: int
    weekly_off: list[int]
