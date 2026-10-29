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
