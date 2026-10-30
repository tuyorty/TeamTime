"""Модели SQLAlchemy.

Три правила (ADR 0002):
1. ``RawMessage`` / ``RawMessageVersion`` только добавляются, текст не перезаписывается.
2. ``SchedulePlan`` и ``Daily`` — версии. Актуальна самая новая с ``retracted_at IS NULL``.
3. У каждой версии есть источник: версия сообщения или ручная правка (+ запись в ``AuditLog``).

Время суток хранится целыми секундами от полуночи (``*_sec``), как в ``teamtime.calc``:
так 24:00 и ночные интервалы представимы без особых случаев.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from teamtime.calc.day import StatusKind
from teamtime.db.base import Base
from teamtime.parsing.types import MessageKind, ParseStatus, PlanDayKind

_ENUMS: dict[str, Enum] = {}


def _enum(cls: type[StrEnum], name: str) -> Enum:
    """Один экземпляр типа на имя: тип ``message_source`` используют несколько таблиц."""
    if name not in _ENUMS:
        _ENUMS[name] = Enum(cls, name=name, values_callable=lambda e: [m.value for m in e])
    return _ENUMS[name]


class Source(StrEnum):
    TELEGRAM = "telegram"
    IMPORT = "import"
    DEMO = "demo"
    MANUAL = "manual"


class Resolution(StrEnum):
    AUTO = "auto"
    """Разобрано без вопросов, в инбоксе не показывается."""
    PENDING = "pending"
    """Ждёт решения в инбоксе."""
    ACCEPTED = "accepted"
    """Принято как есть, несмотря на предупреждения."""
    FIXED = "fixed"
    """Исправлено вручную."""
    IGNORED = "ignored"
    """Не учитывать: производные версии отозваны."""


class TopicKind(StrEnum):
    SCHEDULE = "schedule"
    DAILY = "daily"


class Timestamped:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


# --- справочники -----------------------------------------------------------------------------


class Employee(Timestamped, Base):
    __tablename__ = "employees"

    id: Mapped[int] = mapped_column(primary_key=True)
    full_name: Mapped[str] = mapped_column(String(200))
    short_name: Mapped[str] = mapped_column(String(100), comment="«Иванов И.И.»")
    match_key: Mapped[str] = mapped_column(
        String(100), unique=True, comment="Ключ сопоставления: «иванов ии»"
    )
    position: Mapped[str] = mapped_column(String(200), default="")
    phone: Mapped[str] = mapped_column(String(40), default="", server_default="")
    about: Mapped[str] = mapped_column(String(500), default="", server_default="")
    expertise: Mapped[str] = mapped_column(String(500), default="", server_default="")
    help_with: Mapped[str] = mapped_column(String(500), default="", server_default="")
    avatar_url: Mapped[str] = mapped_column(Text, default="", server_default="")
    monthly_norm_minutes: Mapped[int] = mapped_column(Integer, default=160 * 60)
    hourly_rate: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal(0))
    color: Mapped[str] = mapped_column(String(16), default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    identities: Mapped[list[TelegramIdentity]] = relationship(
        back_populates="employee", foreign_keys="TelegramIdentity.employee_id"
    )

    __table_args__ = (
        CheckConstraint("monthly_norm_minutes >= 0", name="norm_non_negative"),
        CheckConstraint("hourly_rate >= 0", name="rate_non_negative"),
    )


class TelegramIdentity(Base):
    """Аккаунт Telegram. Привязку к сотруднику подтверждает админ, бот лишь предлагает кандидата."""

    __tablename__ = "telegram_identities"

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_user_id: Mapped[int] = mapped_column(BigInteger, unique=True)
    username: Mapped[str | None] = mapped_column(String(64))
    display_name: Mapped[str] = mapped_column(String(200), default="")
    employee_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id", ondelete="SET NULL"))
    suggested_employee_id: Mapped[int | None] = mapped_column(
        ForeignKey("employees.id", ondelete="SET NULL")
    )
    linked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    dm_chat_id: Mapped[int | None] = mapped_column(BigInteger, comment="Личка с ботом, если начата")

    employee: Mapped[Employee | None] = relationship(
        back_populates="identities", foreign_keys=[employee_id]
    )
    suggested_employee: Mapped[Employee | None] = relationship(foreign_keys=[suggested_employee_id])


class DailyReminder(Base):
    """Личные напоминания: попытка фиксируется до обращения в Telegram."""

    __tablename__ = "daily_reminders"

    employee_id: Mapped[int] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), primary_key=True
    )
    work_date: Mapped[date] = mapped_column(Date, primary_key=True)
    chat_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(SmallInteger, default=0, server_default="0")
    deferred_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    snooze_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    snooze_used: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    followup_attempted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    followup_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(80))


class EmployeeTerms(Timestamped, Base):
    """Норма и ставка с месяца действия; прежние месяцы сохраняют свои условия."""

    __tablename__ = "employee_terms"
    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"))
    effective_from: Mapped[date] = mapped_column(Date)
    monthly_norm_minutes: Mapped[int] = mapped_column(Integer)
    hourly_rate: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    created_by: Mapped[str] = mapped_column(String(100), default="admin")
    __table_args__ = (
        UniqueConstraint("employee_id", "effective_from", name="employee_terms_month"),
        CheckConstraint(
            "monthly_norm_minutes >= 0 AND hourly_rate >= 0", name="terms_non_negative"
        ),
    )


class CalculationVersion(Timestamped, Base):
    """Версии правил расчёта; настройки доставки бота применяются независимо."""

    __tablename__ = "calculation_versions"
    id: Mapped[int] = mapped_column(primary_key=True)
    effective_from: Mapped[date] = mapped_column(Date, unique=True)
    value: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_by: Mapped[str] = mapped_column(String(100), default="admin")


class ProjectBonus(Timestamped, Base):
    """Ручная премия за месяц; отмена сохраняет запись и журнал правок."""

    __tablename__ = "project_bonuses"
    id: Mapped[int] = mapped_column(primary_key=True)
    request_id: Mapped[str] = mapped_column(String(36), unique=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id", ondelete="RESTRICT"))
    month: Mapped[date] = mapped_column(Date)
    title: Mapped[str] = mapped_column(String(200))
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    note: Mapped[str] = mapped_column(String(1000), default="", server_default="")
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    created_by: Mapped[str] = mapped_column(String(100), default="admin")
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_reason: Mapped[str] = mapped_column(String(500), default="", server_default="")
    __table_args__ = (
        CheckConstraint("amount > 0 AND amount <= 1000000000", name="bonus_amount"),
        CheckConstraint(
            "EXTRACT(DAY FROM month) = 1 AND month BETWEEN '2000-01-01' AND '2100-12-01'",
            name="bonus_month",
        ),
        Index("ix_project_bonuses_month_employee", "month", "employee_id"),
    )


class StatusRequest(Timestamped, Base):
    """Запрос сотрудника; до одобрения действующие статусы не меняются."""

    __tablename__ = "status_requests"
    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"))
    start: Mapped[date] = mapped_column(Date)
    end: Mapped[date] = mapped_column(Date)
    kind: Mapped[StatusKind | None] = mapped_column(_enum(StatusKind, "status_kind"))
    note: Mapped[str] = mapped_column(String(500), default="", server_default="")
    state: Mapped[str] = mapped_column(String(16), default="pending", server_default="pending")
    requested_by: Mapped[str] = mapped_column(String(100))
    decided_by: Mapped[str | None] = mapped_column(String(100))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision_note: Mapped[str] = mapped_column(String(500), default="", server_default="")
    employee: Mapped[Employee] = relationship()
    __table_args__ = (
        CheckConstraint('"end" >= start', name="status_request_dates"),
        CheckConstraint("state IN ('pending','accepted','rejected')", name="status_request_state"),
        Index("ix_status_requests_state", "state", "created_at"),
    )


class NotificationPreference(Base):
    """Личные настройки без изменения общего расписания или правил расчёта."""

    __tablename__ = "notification_preferences"
    employee_id: Mapped[int] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), primary_key=True
    )
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    delay_minutes: Mapped[int | None] = mapped_column(Integer)
    quiet_start: Mapped[int | None] = mapped_column(Integer)
    quiet_end: Mapped[int | None] = mapped_column(Integer)
    __table_args__ = (
        CheckConstraint("delay_minutes BETWEEN 1 AND 240", name="notification_delay"),
        CheckConstraint(
            "quiet_start BETWEEN 0 AND 1439 AND quiet_end BETWEEN 0 AND 1439",
            name="notification_quiet",
        ),
    )


class BotDraft(Timestamped, Base):
    """Подтверждение мастера дейлика обрабатывается один раз даже при повторе callback."""

    __tablename__ = "bot_drafts"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"))
    user_id: Mapped[int] = mapped_column(BigInteger)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    daily_id: Mapped[int | None] = mapped_column(ForeignKey("dailies.id", ondelete="SET NULL"))


class SystemStatus(Base):
    """Состояние сервиса не зависит от открытого браузера или конкретного процесса API."""

    __tablename__ = "system_status"
    service: Mapped[str] = mapped_column(String(30), primary_key=True)
    state: Mapped[str] = mapped_column(String(20))
    heartbeat_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_update_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(100))
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)


class BotDelivery(Timestamped, Base):
    """История исходящих ответов: сохраняем коды ошибок, без токенов и текста лички."""

    __tablename__ = "bot_deliveries"
    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(20))
    employee_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id", ondelete="SET NULL"))
    raw_message_id: Mapped[int | None] = mapped_column(
        ForeignKey("raw_messages.id", ondelete="SET NULL")
    )
    state: Mapped[str] = mapped_column(String(20), default="attempted")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(100))
    __table_args__ = (Index("ix_bot_deliveries_created", "created_at"),)


class BotChat(Base):
    __tablename__ = "bot_chats"

    chat_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    title: Mapped[str] = mapped_column(String(255), default="")
    is_forum: Mapped[bool] = mapped_column(Boolean, default=False)
    approved: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default="false",
        comment="Разрешён админом на сайте. Сообщения из неразрешённых чатов бот не принимает",
    )
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    topics: Mapped[list[TopicBinding]] = relationship(back_populates="chat")


class TopicBinding(Timestamped, Base):
    """Какая тема форума за что отвечает. ``thread_id`` NULL — весь чат (не форум)."""

    __tablename__ = "topic_bindings"

    id: Mapped[int] = mapped_column(primary_key=True)
    chat_id: Mapped[int] = mapped_column(ForeignKey("bot_chats.chat_id", ondelete="CASCADE"))
    thread_id: Mapped[int | None] = mapped_column(BigInteger)
    kind: Mapped[TopicKind] = mapped_column(_enum(TopicKind, "topic_kind"))
    title: Mapped[str] = mapped_column(String(255), default="")

    chat: Mapped[BotChat] = relationship(back_populates="topics")

    __table_args__ = (
        UniqueConstraint(
            "chat_id", "thread_id", name="chat_thread", postgresql_nulls_not_distinct=True
        ),
    )


# --- исходные сообщения ------------------------------------------------------------------------


class RawMessage(Timestamped, Base):
    __tablename__ = "raw_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    chat_id: Mapped[int] = mapped_column(BigInteger)
    message_id: Mapped[int] = mapped_column(BigInteger)
    thread_id: Mapped[int | None] = mapped_column(BigInteger)
    author_tg_id: Mapped[int | None] = mapped_column(BigInteger)
    author_name: Mapped[str] = mapped_column(String(200), default="")
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    source: Mapped[Source] = mapped_column(_enum(Source, "message_source"))
    latest_version: Mapped[int] = mapped_column(Integer, default=1)
    bot_reply_message_id: Mapped[int | None] = mapped_column(
        BigInteger, comment="Служебный ответ бота в теме (если был), чтобы удалить при исправлении"
    )

    versions: Mapped[list[RawMessageVersion]] = relationship(
        back_populates="message", order_by="RawMessageVersion.version"
    )

    __table_args__ = (
        UniqueConstraint("chat_id", "message_id", name="chat_message"),
        Index("ix_raw_messages_author_sent", "author_tg_id", "sent_at"),
    )


class RawMessageVersion(Base):
    __tablename__ = "raw_message_versions"

    id: Mapped[int] = mapped_column(primary_key=True)
    raw_message_id: Mapped[int] = mapped_column(ForeignKey("raw_messages.id", ondelete="CASCADE"))
    version: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)
    edited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    message: Mapped[RawMessage] = relationship(back_populates="versions")

    __table_args__ = (UniqueConstraint("raw_message_id", "version", name="message_version"),)


class ParseResultRow(Timestamped, Base):
    """Результат разбора конкретной версии текста. Переразбор добавляет новую строку."""

    __tablename__ = "parse_results"

    id: Mapped[int] = mapped_column(primary_key=True)
    message_version_id: Mapped[int] = mapped_column(
        ForeignKey("raw_message_versions.id", ondelete="CASCADE")
    )
    parser_version: Mapped[int] = mapped_column(SmallInteger)
    kind: Mapped[MessageKind] = mapped_column(_enum(MessageKind, "message_kind"))
    status: Mapped[ParseStatus] = mapped_column(_enum(ParseStatus, "parse_status"))
    issues: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, default=list)
    data: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    employee_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id", ondelete="SET NULL"))
    employee_unresolved: Mapped[bool] = mapped_column(Boolean, default=False)
    resolution: Mapped[Resolution] = mapped_column(_enum(Resolution, "resolution"))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_latest: Mapped[bool] = mapped_column(Boolean, default=True)

    version: Mapped[RawMessageVersion] = relationship()
    employee: Mapped[Employee | None] = relationship()

    __table_args__ = (
        Index(
            "ix_parse_results_inbox",
            "resolution",
            "created_at",
            postgresql_where=text("is_latest"),
        ),
    )


# --- планы -------------------------------------------------------------------------------------


class SchedulePlan(Timestamped, Base):
    __tablename__ = "schedule_plans"

    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"))
    iso_year: Mapped[int] = mapped_column(SmallInteger)
    iso_week: Mapped[int] = mapped_column(SmallInteger)
    week_start: Mapped[date] = mapped_column(Date)
    sprint_start: Mapped[date] = mapped_column(Date)
    sprint_end: Mapped[date] = mapped_column(Date)
    version: Mapped[int] = mapped_column(Integer)
    source: Mapped[Source] = mapped_column(_enum(Source, "message_source"))
    source_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("raw_message_versions.id", ondelete="SET NULL")
    )
    parse_result_id: Mapped[int | None] = mapped_column(
        ForeignKey("parse_results.id", ondelete="SET NULL")
    )
    created_by: Mapped[str] = mapped_column(String(100), default="bot")
    retracted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    edited: Mapped[bool] = mapped_column(
        Boolean, default=False, comment="Из отредактированного сообщения"
    )

    employee: Mapped[Employee] = relationship()
    days: Mapped[list[PlanDay]] = relationship(
        back_populates="plan", cascade="all, delete-orphan", order_by="PlanDay.date"
    )
    tasks: Mapped[list[SprintTask]] = relationship(
        back_populates="plan", cascade="all, delete-orphan", order_by="SprintTask.position"
    )
    source_version: Mapped[RawMessageVersion | None] = relationship()

    __table_args__ = (
        UniqueConstraint(
            "employee_id", "iso_year", "iso_week", "version", name="employee_week_version"
        ),
        Index("ix_schedule_plans_current", "employee_id", "week_start", "version"),
    )


class PlanDay(Base):
    __tablename__ = "plan_days"

    id: Mapped[int] = mapped_column(primary_key=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("schedule_plans.id", ondelete="CASCADE"))
    date: Mapped[date] = mapped_column(Date)
    kind: Mapped[PlanDayKind] = mapped_column(_enum(PlanDayKind, "plan_day_kind"))
    start_sec: Mapped[int | None] = mapped_column(Integer)
    end_sec: Mapped[int | None] = mapped_column(Integer)
    planned_sec: Mapped[int | None] = mapped_column(Integer)
    intervals: Mapped[list[list[int]]] = mapped_column(JSONB, default=list)
    note: Mapped[str | None] = mapped_column(Text)
    note_has_time: Mapped[bool] = mapped_column(Boolean, default=False)
    raw_line: Mapped[str] = mapped_column(Text, default="")

    plan: Mapped[SchedulePlan] = relationship(back_populates="days")

    __table_args__ = (UniqueConstraint("plan_id", "date", name="plan_date"),)


class SprintTask(Base):
    __tablename__ = "sprint_tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("schedule_plans.id", ondelete="CASCADE"))
    position: Mapped[int] = mapped_column(SmallInteger)
    text: Mapped[str] = mapped_column(Text)

    plan: Mapped[SchedulePlan] = relationship(back_populates="tasks")


# --- факт --------------------------------------------------------------------------------------


class Daily(Timestamped, Base):
    __tablename__ = "dailies"

    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"))
    work_date: Mapped[date] = mapped_column(Date)
    version: Mapped[int] = mapped_column(Integer)
    efficiency: Mapped[int | None] = mapped_column(SmallInteger)
    source: Mapped[Source] = mapped_column(_enum(Source, "message_source"))
    source_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("raw_message_versions.id", ondelete="SET NULL")
    )
    parse_result_id: Mapped[int | None] = mapped_column(
        ForeignKey("parse_results.id", ondelete="SET NULL")
    )
    created_by: Mapped[str] = mapped_column(String(100), default="bot")
    retracted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    edited: Mapped[bool] = mapped_column(Boolean, default=False)
    sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), comment="Когда прислан (для «прислал с опозданием»)"
    )

    employee: Mapped[Employee] = relationship()
    intervals: Mapped[list[DailyInterval]] = relationship(
        back_populates="daily", cascade="all, delete-orphan", order_by="DailyInterval.position"
    )
    tasks: Mapped[list[DailyTask]] = relationship(
        back_populates="daily", cascade="all, delete-orphan", order_by="DailyTask.position"
    )
    source_version: Mapped[RawMessageVersion | None] = relationship()

    __table_args__ = (
        UniqueConstraint("employee_id", "work_date", "version", name="employee_date_version"),
        CheckConstraint(
            "efficiency IS NULL OR efficiency BETWEEN 0 AND 100", name="efficiency_range"
        ),
        Index("ix_dailies_date", "work_date"),
    )


class DailyInterval(Base):
    __tablename__ = "daily_intervals"

    id: Mapped[int] = mapped_column(primary_key=True)
    daily_id: Mapped[int] = mapped_column(ForeignKey("dailies.id", ondelete="CASCADE"))
    position: Mapped[int] = mapped_column(SmallInteger)
    start_sec: Mapped[int] = mapped_column(Integer)
    end_sec: Mapped[int] = mapped_column(Integer)

    daily: Mapped[Daily] = relationship(back_populates="intervals")

    __table_args__ = (
        CheckConstraint(
            "start_sec BETWEEN 0 AND 86400 AND end_sec BETWEEN 0 AND 86400", name="day_range"
        ),
    )


class DailyTask(Base):
    __tablename__ = "daily_tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    daily_id: Mapped[int] = mapped_column(ForeignKey("dailies.id", ondelete="CASCADE"))
    position: Mapped[int] = mapped_column(SmallInteger)
    text: Mapped[str] = mapped_column(Text)

    daily: Mapped[Daily] = relationship(back_populates="tasks")


class DayStatus(Timestamped, Base):
    """Отпуск, больничный, удалёнка… Активна одна запись на день (частичный уникальный индекс)."""

    __tablename__ = "day_statuses"

    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"))
    date: Mapped[date] = mapped_column(Date)
    kind: Mapped[StatusKind] = mapped_column(_enum(StatusKind, "status_kind"))
    note: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[str] = mapped_column(String(100))
    retracted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    employee: Mapped[Employee] = relationship()

    __table_args__ = (
        Index(
            "uq_day_statuses_active",
            "employee_id",
            "date",
            unique=True,
            postgresql_where=text("retracted_at IS NULL"),
        ),
    )


# --- служебное ---------------------------------------------------------------------------------


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    actor: Mapped[str] = mapped_column(String(100), comment="admin | bot:<tg id> | system")
    action: Mapped[str] = mapped_column(String(64))
    entity_type: Mapped[str] = mapped_column(String(64))
    entity_id: Mapped[str] = mapped_column(String(64), default="")
    employee_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id", ondelete="SET NULL"))
    before: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    after: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    reason: Mapped[str] = mapped_column(Text, default="")


class AppSetting(Base):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[dict[str, Any]] = mapped_column(JSONB)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
