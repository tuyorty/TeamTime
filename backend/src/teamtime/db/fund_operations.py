"""Операции фонда, обязательства и подтверждения; деньги меняются только проводками."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from teamtime.db.base import Base
from teamtime.db.models import Timestamped


class FundBasket(Timestamped, Base):
    __tablename__ = "fund_baskets"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("fund_members.employee_id"))
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class FundOperation(Timestamped, Base):
    __tablename__ = "fund_operations"
    id: Mapped[int] = mapped_column(primary_key=True)
    request_id: Mapped[str] = mapped_column(String(36), unique=True)
    payload_hash: Mapped[str] = mapped_column(String(64))
    kind: Mapped[str] = mapped_column(String(40))
    state: Mapped[str] = mapped_column(String(16), default="draft")
    occurred_on: Mapped[date] = mapped_column(Date, index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    basket_id: Mapped[int | None] = mapped_column(ForeignKey("fund_baskets.id"))
    target_basket_id: Mapped[int | None] = mapped_column(ForeignKey("fund_baskets.id"))
    employee_id: Mapped[int | None] = mapped_column(ForeignKey("fund_members.employee_id"))
    details: Mapped[dict[str, Any]] = mapped_column(JSONB)
    reason: Mapped[str] = mapped_column(Text)
    created_by: Mapped[int] = mapped_column(ForeignKey("fund_members.employee_id"))
    confirmed_by: Mapped[int | None] = mapped_column(ForeignKey("fund_members.employee_id"))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    consented_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reverses_id: Mapped[int | None] = mapped_column(ForeignKey("fund_operations.id"), unique=True)
    __table_args__ = (
        CheckConstraint("state IN ('draft','posted','cancelled')", name="state"),
        CheckConstraint("amount >= 0", name="amount"),
    )


class FundPosting(Timestamped, Base):
    __tablename__ = "fund_postings"
    id: Mapped[int] = mapped_column(primary_key=True)
    operation_id: Mapped[int] = mapped_column(ForeignKey("fund_operations.id"), index=True)
    account: Mapped[str] = mapped_column(String(24), index=True)
    account_id: Mapped[int] = mapped_column(Integer, index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    __table_args__ = (
        CheckConstraint(
            "account IN ('cash','obligation','loan','overpayment','unallocated')", name="account"
        ),
        UniqueConstraint("operation_id", "account", "account_id"),
    )


class FundObligation(Timestamped, Base):
    __tablename__ = "fund_obligations"
    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("fund_members.employee_id"), index=True)
    month: Mapped[date] = mapped_column(Date, index=True)
    kind: Mapped[str] = mapped_column(String(20))
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    origin: Mapped[str] = mapped_column(String(100), unique=True)
    title: Mapped[str] = mapped_column(String(200))
    __table_args__ = (
        CheckConstraint("amount >= 0", name="amount"),
        CheckConstraint("kind IN ('salary','compensation')", name="kind"),
    )


class FundClaim(Timestamped, Base):
    __tablename__ = "fund_claims"
    id: Mapped[int] = mapped_column(primary_key=True)
    request_id: Mapped[str] = mapped_column(String(36), unique=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("fund_members.employee_id"), index=True)
    month: Mapped[date] = mapped_column(Date)
    spent_on: Mapped[date] = mapped_column(Date)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    title: Mapped[str] = mapped_column(String(200))
    state: Mapped[str] = mapped_column(String(16), default="pending")
    decided_by: Mapped[int | None] = mapped_column(ForeignKey("fund_members.employee_id"))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision_reason: Mapped[str] = mapped_column(Text, default="")
    __table_args__ = (
        CheckConstraint("amount > 0", name="amount"),
        CheckConstraint("state IN ('pending','approved','rejected','cancelled')", name="state"),
    )


class FundAttachment(Timestamped, Base):
    __tablename__ = "fund_attachments"
    id: Mapped[int] = mapped_column(primary_key=True)
    claim_id: Mapped[int] = mapped_column(ForeignKey("fund_claims.id"), index=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("fund_members.employee_id"))
    name: Mapped[str] = mapped_column(String(200))
    content_type: Mapped[str] = mapped_column(String(100))
    data: Mapped[bytes] = mapped_column(LargeBinary)


class FundLoan(Timestamped, Base):
    __tablename__ = "fund_loans"
    id: Mapped[int] = mapped_column(primary_key=True)
    request_id: Mapped[str] = mapped_column(String(36), unique=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("fund_members.employee_id"), index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    issued_on: Mapped[date] = mapped_column(Date)
    due_on: Mapped[date] = mapped_column(Date)
    reason: Mapped[str] = mapped_column(Text)
    approved_by: Mapped[int] = mapped_column(ForeignKey("fund_members.employee_id"))
    issued: Mapped[bool] = mapped_column(Boolean, default=False)
    __table_args__ = (CheckConstraint("amount > 0 AND due_on > issued_on", name="terms"),)


class FundReconciliation(Timestamped, Base):
    __tablename__ = "fund_reconciliations"
    id: Mapped[int] = mapped_column(primary_key=True)
    request_id: Mapped[str] = mapped_column(String(36), unique=True)
    basket_id: Mapped[int] = mapped_column(ForeignKey("fund_baskets.id"))
    as_of: Mapped[date] = mapped_column(Date)
    actual: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    expected: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    confirmed_by: Mapped[int] = mapped_column(ForeignKey("fund_members.employee_id"))
    reason: Mapped[str] = mapped_column(Text)


class FundTimeRequest(Timestamped, Base):
    __tablename__ = "fund_time_requests"
    id: Mapped[int] = mapped_column(primary_key=True)
    request_id: Mapped[str] = mapped_column(String(36), unique=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("fund_members.employee_id"), index=True)
    kind: Mapped[str] = mapped_column(String(24))
    days: Mapped[list[str]] = mapped_column(JSONB)
    seconds: Mapped[int] = mapped_column(Integer, default=0)
    reason: Mapped[str] = mapped_column(String(500))
    state: Mapped[str] = mapped_column(String(16), default="pending")
    evidence: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    decided_by: Mapped[int | None] = mapped_column(ForeignKey("fund_members.employee_id"))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    decision_reason: Mapped[str] = mapped_column(Text, default="")
    __table_args__ = (
        CheckConstraint(
            "kind IN ('vacation','sick','trip','missed','waiver','no_work')", name="kind"
        ),
        CheckConstraint("state IN ('pending','approved','rejected','cancelled')", name="state"),
    )


class FundVacationYear(Timestamped, Base):
    __tablename__ = "fund_vacation_years"
    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("fund_members.employee_id"))
    start: Mapped[date] = mapped_column(Date)
    end: Mapped[date] = mapped_column(Date)
    as_of: Mapped[date] = mapped_column(Date)
    annual_days: Mapped[int] = mapped_column(Integer, default=28)
    opening_days: Mapped[int] = mapped_column(Integer)
    adjustment_days: Mapped[int] = mapped_column(Integer, default=0)
    reason: Mapped[str] = mapped_column(Text)
    approved_by: Mapped[int] = mapped_column(ForeignKey("fund_members.employee_id"))
    __table_args__ = (
        UniqueConstraint("employee_id", "start"),
        CheckConstraint(
            'start <= as_of AND as_of <= "end" AND annual_days >= 0 AND opening_days >= 0',
            name="values",
        ),
    )


class FundAdjustment(Timestamped, Base):
    __tablename__ = "fund_adjustments"
    id: Mapped[int] = mapped_column(primary_key=True)
    request_id: Mapped[str] = mapped_column(String(36), unique=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("fund_members.employee_id"), index=True)
    kind: Mapped[str] = mapped_column(String(32))
    origin_month: Mapped[date] = mapped_column(Date)
    applied_month: Mapped[date] = mapped_column(Date)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    before: Mapped[dict[str, Any]] = mapped_column(JSONB)
    after: Mapped[dict[str, Any]] = mapped_column(JSONB)
    reason: Mapped[str] = mapped_column(Text)
    state: Mapped[str] = mapped_column(String(16), default="pending")
    created_by: Mapped[int] = mapped_column(ForeignKey("fund_members.employee_id"))
    approved_by: Mapped[int | None] = mapped_column(ForeignKey("fund_members.employee_id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        CheckConstraint("kind IN ('bonus','salary','compensation','source')", name="kind"),
        CheckConstraint("state IN ('pending','approved','rejected')", name="state"),
    )


class FundOpening(Timestamped, Base):
    __tablename__ = "fund_openings"
    employee_id: Mapped[int] = mapped_column(
        ForeignKey("fund_members.employee_id"), primary_key=True
    )
    month: Mapped[date] = mapped_column(Date)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    approved_by: Mapped[int] = mapped_column(ForeignKey("fund_members.employee_id"))
    reason: Mapped[str] = mapped_column(Text)
    __table_args__ = (CheckConstraint("amount >= 0", name="amount"),)


class FundNotification(Timestamped, Base):
    __tablename__ = "fund_notifications"
    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("fund_members.employee_id"))
    cycle: Mapped[str] = mapped_column(String(100))
    attempted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(String(100))
    __table_args__ = (UniqueConstraint("employee_id", "cycle"),)


class FundImport(Timestamped, Base):
    __tablename__ = "fund_imports"
    package_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    digest: Mapped[str] = mapped_column(String(64))
    as_of: Mapped[date] = mapped_column(Date)
    source: Mapped[str] = mapped_column(Text)
    manifest: Mapped[dict[str, Any]] = mapped_column(JSONB)
    applied_by: Mapped[int] = mapped_column(ForeignKey("fund_members.employee_id"))


class TeamLogin(Timestamped, Base):
    __tablename__ = "team_logins"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    secret_hash: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    telegram_id: Mapped[int | None] = mapped_column(BigInteger)
    employee_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TeamSession(Timestamped, Base):
    __tablename__ = "team_sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    employee_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"))
    identity_id: Mapped[int | None] = mapped_column(ForeignKey("telegram_identities.id"))
    scope: Mapped[str] = mapped_column(String(16), default="member")
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
