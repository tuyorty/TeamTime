"""Хранилище фонда: отдельные версии условий, календаря и поступлений."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from teamtime.db.base import Base
from teamtime.db.models import Timestamped


class FundMember(Timestamped, Base):
    """Финансовые права назначаются человеку, а не общей технической сессии админа."""

    __tablename__ = "fund_members"
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), primary_key=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    leader: Mapped[bool] = mapped_column(Boolean, default=False)
    joined_on: Mapped[date] = mapped_column(Date)
    left_on: Mapped[date | None] = mapped_column(Date)
    appointed_by: Mapped[str] = mapped_column(String(100))
    __table_args__ = (CheckConstraint("left_on IS NULL OR left_on >= joined_on", name="dates"),)


class FundCalendar(Timestamped, Base):
    __tablename__ = "fund_calendars"
    id: Mapped[int] = mapped_column(primary_key=True)
    month: Mapped[date] = mapped_column(Date, index=True)
    version: Mapped[int] = mapped_column(Integer)
    source: Mapped[str] = mapped_column(Text)
    source_version: Mapped[str] = mapped_column(String(100))
    days: Mapped[dict[str, int]] = mapped_column(JSONB)
    holidays: Mapped[list[str]] = mapped_column(JSONB)
    created_by: Mapped[int] = mapped_column(ForeignKey("fund_members.employee_id"))
    reason: Mapped[str] = mapped_column(Text)
    __table_args__ = (
        UniqueConstraint("month", "version"),
        CheckConstraint("EXTRACT(DAY FROM month) = 1 AND version >= 1", name="month_version"),
    )


class FundTerms(Timestamped, Base):
    __tablename__ = "fund_terms"
    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("fund_members.employee_id"), index=True)
    effective_from: Mapped[date] = mapped_column(Date)
    revision: Mapped[int] = mapped_column(Integer)
    target: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    share: Mapped[Decimal] = mapped_column(Numeric(8, 4))
    sources: Mapped[list[str]] = mapped_column(JSONB)
    no_other_income: Mapped[bool] = mapped_column(Boolean)
    created_by: Mapped[int] = mapped_column(ForeignKey("fund_members.employee_id"))
    reason: Mapped[str] = mapped_column(Text)
    __table_args__ = (
        UniqueConstraint("employee_id", "effective_from", "revision"),
        CheckConstraint("target >= 0 AND share > 0 AND revision >= 1", name="values"),
    )


class FundPeriod(Timestamped, Base):
    """Неизменяемый снимок месяца с версией правил и всеми исходными данными."""

    __tablename__ = "fund_periods"
    month: Mapped[date] = mapped_column(Date, primary_key=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_by: Mapped[int | None] = mapped_column(ForeignKey("fund_members.employee_id"))
    snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    __table_args__ = (
        CheckConstraint("EXTRACT(DAY FROM month) = 1", name="month"),
        CheckConstraint(
            "(closed_at IS NULL AND closed_by IS NULL AND snapshot IS NULL) OR "
            "(closed_at IS NOT NULL AND closed_by IS NOT NULL AND snapshot IS NOT NULL)",
            name="closure",
        ),
    )


class FundReceipt(Timestamped, Base):
    """Фактическое поступление источника: не движение денег в общей корзине."""

    __tablename__ = "fund_receipts"
    id: Mapped[int] = mapped_column(primary_key=True)
    request_id: Mapped[str] = mapped_column(String(36), unique=True)
    payload_hash: Mapped[str] = mapped_column(String(64))
    employee_id: Mapped[int] = mapped_column(ForeignKey("fund_members.employee_id"), index=True)
    source: Mapped[str] = mapped_column(String(100))
    origin_month: Mapped[date] = mapped_column(Date)
    applied_month: Mapped[date] = mapped_column(ForeignKey("fund_periods.month"))
    received_on: Mapped[date] = mapped_column(Date)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    created_by: Mapped[int] = mapped_column(ForeignKey("fund_members.employee_id"))
    __table_args__ = (
        CheckConstraint("amount > 0", name="positive"),
        CheckConstraint("EXTRACT(DAY FROM origin_month) = 1", name="origin_month"),
    )


class FundSourceState(Timestamped, Base):
    """Подтверждение полноты источника, включая явный ноль; это не запись о выплате."""

    __tablename__ = "fund_source_states"
    employee_id: Mapped[int] = mapped_column(
        ForeignKey("fund_members.employee_id"), primary_key=True
    )
    month: Mapped[date] = mapped_column(ForeignKey("fund_periods.month"), primary_key=True)
    source: Mapped[str] = mapped_column(String(100), primary_key=True)
    version: Mapped[int] = mapped_column(Integer)
    complete: Mapped[bool] = mapped_column(Boolean)
    confirmed_total: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    changed_by: Mapped[int] = mapped_column(ForeignKey("fund_members.employee_id"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    __table_args__ = (CheckConstraint("version >= 1", name="values"),)


class FundAudit(Timestamped, Base):
    """Общая история содержит только учётные сведения без исходного личного сообщения."""

    __tablename__ = "fund_audit"
    id: Mapped[int] = mapped_column(primary_key=True)
    actor_id: Mapped[int] = mapped_column(ForeignKey("fund_members.employee_id"))
    action: Mapped[str] = mapped_column(String(80))
    data: Mapped[dict[str, Any]] = mapped_column(JSONB)
