"""Именной доступ, журнал фонда, согласования и неизменяемая история

Revision ID: f8a1b2c3d4e5
Revises: e7f0a1b2c3d4
Create Date: 2026-11-05 15:26:47.615186+00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "f8a1b2c3d4e5"
down_revision: str | None = "e7f0a1b2c3d4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "team_logins",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("secret_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("telegram_id", sa.BigInteger(), nullable=True),
        sa.Column("employee_id", sa.Integer(), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["employee_id"], ["employees.id"], name=op.f("fk_team_logins_employee_id_employees")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_team_logins")),
    )
    op.create_table(
        "fund_adjustments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("request_id", sa.String(length=36), nullable=False),
        sa.Column("employee_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("origin_month", sa.Date(), nullable=False),
        sa.Column("applied_month", sa.Date(), nullable=False),
        sa.Column("amount", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("before", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("after", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column("approved_by", sa.Integer(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "kind IN ('bonus','salary','compensation','source')",
            name=op.f("ck_fund_adjustments_kind"),
        ),
        sa.CheckConstraint(
            "state IN ('pending','approved','rejected')", name=op.f("ck_fund_adjustments_state")
        ),
        sa.ForeignKeyConstraint(
            ["approved_by"],
            ["fund_members.employee_id"],
            name=op.f("fk_fund_adjustments_approved_by_fund_members"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["fund_members.employee_id"],
            name=op.f("fk_fund_adjustments_created_by_fund_members"),
        ),
        sa.ForeignKeyConstraint(
            ["employee_id"],
            ["fund_members.employee_id"],
            name=op.f("fk_fund_adjustments_employee_id_fund_members"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_fund_adjustments")),
        sa.UniqueConstraint("request_id", name=op.f("uq_fund_adjustments_request_id")),
    )
    op.create_index(
        op.f("ix_fund_adjustments_employee_id"), "fund_adjustments", ["employee_id"], unique=False
    )
    op.create_table(
        "fund_baskets",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["fund_members.employee_id"],
            name=op.f("fk_fund_baskets_owner_id_fund_members"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_fund_baskets")),
        sa.UniqueConstraint("name", name=op.f("uq_fund_baskets_name")),
    )
    op.create_table(
        "fund_claims",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("request_id", sa.String(length=36), nullable=False),
        sa.Column("employee_id", sa.Integer(), nullable=False),
        sa.Column("month", sa.Date(), nullable=False),
        sa.Column("spent_on", sa.Date(), nullable=False),
        sa.Column("amount", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("decided_by", sa.Integer(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision_reason", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "state IN ('pending','approved','rejected','cancelled')",
            name=op.f("ck_fund_claims_state"),
        ),
        sa.CheckConstraint("amount > 0", name=op.f("ck_fund_claims_amount")),
        sa.ForeignKeyConstraint(
            ["decided_by"],
            ["fund_members.employee_id"],
            name=op.f("fk_fund_claims_decided_by_fund_members"),
        ),
        sa.ForeignKeyConstraint(
            ["employee_id"],
            ["fund_members.employee_id"],
            name=op.f("fk_fund_claims_employee_id_fund_members"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_fund_claims")),
        sa.UniqueConstraint("request_id", name=op.f("uq_fund_claims_request_id")),
    )
    op.create_index(
        op.f("ix_fund_claims_employee_id"), "fund_claims", ["employee_id"], unique=False
    )
    op.create_table(
        "fund_imports",
        sa.Column("package_id", sa.String(length=100), nullable=False),
        sa.Column("digest", sa.String(length=64), nullable=False),
        sa.Column("as_of", sa.Date(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("manifest", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("applied_by", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["applied_by"],
            ["fund_members.employee_id"],
            name=op.f("fk_fund_imports_applied_by_fund_members"),
        ),
        sa.PrimaryKeyConstraint("package_id", name=op.f("pk_fund_imports")),
    )
    op.create_table(
        "fund_loans",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("request_id", sa.String(length=36), nullable=False),
        sa.Column("employee_id", sa.Integer(), nullable=False),
        sa.Column("amount", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("issued_on", sa.Date(), nullable=False),
        sa.Column("due_on", sa.Date(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("approved_by", sa.Integer(), nullable=False),
        sa.Column("issued", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("amount > 0 AND due_on > issued_on", name=op.f("ck_fund_loans_terms")),
        sa.ForeignKeyConstraint(
            ["approved_by"],
            ["fund_members.employee_id"],
            name=op.f("fk_fund_loans_approved_by_fund_members"),
        ),
        sa.ForeignKeyConstraint(
            ["employee_id"],
            ["fund_members.employee_id"],
            name=op.f("fk_fund_loans_employee_id_fund_members"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_fund_loans")),
        sa.UniqueConstraint("request_id", name=op.f("uq_fund_loans_request_id")),
    )
    op.create_index(op.f("ix_fund_loans_employee_id"), "fund_loans", ["employee_id"], unique=False)
    op.create_table(
        "fund_notifications",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("employee_id", sa.Integer(), nullable=False),
        sa.Column("cycle", sa.String(length=100), nullable=False),
        sa.Column("attempted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.String(length=100), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["employee_id"],
            ["fund_members.employee_id"],
            name=op.f("fk_fund_notifications_employee_id_fund_members"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_fund_notifications")),
        sa.UniqueConstraint(
            "employee_id", "cycle", name=op.f("uq_fund_notifications_employee_id_cycle")
        ),
    )
    op.create_table(
        "fund_obligations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("employee_id", sa.Integer(), nullable=False),
        sa.Column("month", sa.Date(), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("amount", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("origin", sa.String(length=100), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "kind IN ('salary','compensation')", name=op.f("ck_fund_obligations_kind")
        ),
        sa.CheckConstraint("amount >= 0", name=op.f("ck_fund_obligations_amount")),
        sa.ForeignKeyConstraint(
            ["employee_id"],
            ["fund_members.employee_id"],
            name=op.f("fk_fund_obligations_employee_id_fund_members"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_fund_obligations")),
        sa.UniqueConstraint("origin", name=op.f("uq_fund_obligations_origin")),
    )
    op.create_index(
        op.f("ix_fund_obligations_employee_id"), "fund_obligations", ["employee_id"], unique=False
    )
    op.create_index(op.f("ix_fund_obligations_month"), "fund_obligations", ["month"], unique=False)
    op.create_table(
        "fund_openings",
        sa.Column("employee_id", sa.Integer(), nullable=False),
        sa.Column("month", sa.Date(), nullable=False),
        sa.Column("amount", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("approved_by", sa.Integer(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("amount >= 0", name=op.f("ck_fund_openings_amount")),
        sa.ForeignKeyConstraint(
            ["approved_by"],
            ["fund_members.employee_id"],
            name=op.f("fk_fund_openings_approved_by_fund_members"),
        ),
        sa.ForeignKeyConstraint(
            ["employee_id"],
            ["fund_members.employee_id"],
            name=op.f("fk_fund_openings_employee_id_fund_members"),
        ),
        sa.PrimaryKeyConstraint("employee_id", name=op.f("pk_fund_openings")),
    )
    op.create_table(
        "fund_time_requests",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("request_id", sa.String(length=36), nullable=False),
        sa.Column("employee_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=24), nullable=False),
        sa.Column("days", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("seconds", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(length=500), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("evidence", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("decided_by", sa.Integer(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision_reason", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "kind IN ('vacation','sick','trip','missed','waiver','no_work')",
            name=op.f("ck_fund_time_requests_kind"),
        ),
        sa.CheckConstraint(
            "state IN ('pending','approved','rejected','cancelled')",
            name=op.f("ck_fund_time_requests_state"),
        ),
        sa.ForeignKeyConstraint(
            ["decided_by"],
            ["fund_members.employee_id"],
            name=op.f("fk_fund_time_requests_decided_by_fund_members"),
        ),
        sa.ForeignKeyConstraint(
            ["employee_id"],
            ["fund_members.employee_id"],
            name=op.f("fk_fund_time_requests_employee_id_fund_members"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_fund_time_requests")),
        sa.UniqueConstraint("request_id", name=op.f("uq_fund_time_requests_request_id")),
    )
    op.create_index(
        op.f("ix_fund_time_requests_employee_id"),
        "fund_time_requests",
        ["employee_id"],
        unique=False,
    )
    op.create_table(
        "fund_vacation_years",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("employee_id", sa.Integer(), nullable=False),
        sa.Column("start", sa.Date(), nullable=False),
        sa.Column("end", sa.Date(), nullable=False),
        sa.Column("as_of", sa.Date(), nullable=False),
        sa.Column("annual_days", sa.Integer(), nullable=False),
        sa.Column("opening_days", sa.Integer(), nullable=False),
        sa.Column("adjustment_days", sa.Integer(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("approved_by", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            'start <= as_of AND as_of <= "end" AND annual_days >= 0 AND opening_days >= 0',
            name=op.f("ck_fund_vacation_years_values"),
        ),
        sa.ForeignKeyConstraint(
            ["approved_by"],
            ["fund_members.employee_id"],
            name=op.f("fk_fund_vacation_years_approved_by_fund_members"),
        ),
        sa.ForeignKeyConstraint(
            ["employee_id"],
            ["fund_members.employee_id"],
            name=op.f("fk_fund_vacation_years_employee_id_fund_members"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_fund_vacation_years")),
        sa.UniqueConstraint(
            "employee_id", "start", name=op.f("uq_fund_vacation_years_employee_id_start")
        ),
    )
    op.create_table(
        "team_sessions",
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("employee_id", sa.Integer(), nullable=True),
        sa.Column("identity_id", sa.Integer(), nullable=True),
        sa.Column("scope", sa.String(length=16), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["employee_id"], ["employees.id"], name=op.f("fk_team_sessions_employee_id_employees")
        ),
        sa.ForeignKeyConstraint(
            ["identity_id"],
            ["telegram_identities.id"],
            name=op.f("fk_team_sessions_identity_id_telegram_identities"),
        ),
        sa.PrimaryKeyConstraint("token_hash", name=op.f("pk_team_sessions")),
    )
    op.create_table(
        "fund_attachments",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("claim_id", sa.Integer(), nullable=False),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("content_type", sa.String(length=100), nullable=False),
        sa.Column("data", sa.LargeBinary(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["claim_id"], ["fund_claims.id"], name=op.f("fk_fund_attachments_claim_id_fund_claims")
        ),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["fund_members.employee_id"],
            name=op.f("fk_fund_attachments_owner_id_fund_members"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_fund_attachments")),
    )
    op.create_index(
        op.f("ix_fund_attachments_claim_id"), "fund_attachments", ["claim_id"], unique=False
    )
    op.create_table(
        "fund_operations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("request_id", sa.String(length=36), nullable=False),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("occurred_on", sa.Date(), nullable=False),
        sa.Column("amount", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("basket_id", sa.Integer(), nullable=True),
        sa.Column("target_basket_id", sa.Integer(), nullable=True),
        sa.Column("employee_id", sa.Integer(), nullable=True),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column("confirmed_by", sa.Integer(), nullable=True),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consented_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reverses_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "state IN ('draft','posted','cancelled')", name=op.f("ck_fund_operations_state")
        ),
        sa.CheckConstraint("amount >= 0", name=op.f("ck_fund_operations_amount")),
        sa.ForeignKeyConstraint(
            ["basket_id"],
            ["fund_baskets.id"],
            name=op.f("fk_fund_operations_basket_id_fund_baskets"),
        ),
        sa.ForeignKeyConstraint(
            ["confirmed_by"],
            ["fund_members.employee_id"],
            name=op.f("fk_fund_operations_confirmed_by_fund_members"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["fund_members.employee_id"],
            name=op.f("fk_fund_operations_created_by_fund_members"),
        ),
        sa.ForeignKeyConstraint(
            ["employee_id"],
            ["fund_members.employee_id"],
            name=op.f("fk_fund_operations_employee_id_fund_members"),
        ),
        sa.ForeignKeyConstraint(
            ["reverses_id"],
            ["fund_operations.id"],
            name=op.f("fk_fund_operations_reverses_id_fund_operations"),
        ),
        sa.ForeignKeyConstraint(
            ["target_basket_id"],
            ["fund_baskets.id"],
            name=op.f("fk_fund_operations_target_basket_id_fund_baskets"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_fund_operations")),
        sa.UniqueConstraint("request_id", name=op.f("uq_fund_operations_request_id")),
        sa.UniqueConstraint("reverses_id", name=op.f("uq_fund_operations_reverses_id")),
    )
    op.create_index(
        op.f("ix_fund_operations_occurred_on"), "fund_operations", ["occurred_on"], unique=False
    )
    op.create_table(
        "fund_reconciliations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("request_id", sa.String(length=36), nullable=False),
        sa.Column("basket_id", sa.Integer(), nullable=False),
        sa.Column("as_of", sa.Date(), nullable=False),
        sa.Column("actual", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("expected", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("confirmed_by", sa.Integer(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["basket_id"],
            ["fund_baskets.id"],
            name=op.f("fk_fund_reconciliations_basket_id_fund_baskets"),
        ),
        sa.ForeignKeyConstraint(
            ["confirmed_by"],
            ["fund_members.employee_id"],
            name=op.f("fk_fund_reconciliations_confirmed_by_fund_members"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_fund_reconciliations")),
        sa.UniqueConstraint("request_id", name=op.f("uq_fund_reconciliations_request_id")),
    )
    op.create_table(
        "fund_postings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("operation_id", sa.Integer(), nullable=False),
        sa.Column("account", sa.String(length=24), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("amount", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "account IN ('cash','obligation','loan','overpayment','unallocated')",
            name=op.f("ck_fund_postings_account"),
        ),
        sa.ForeignKeyConstraint(
            ["operation_id"],
            ["fund_operations.id"],
            name=op.f("fk_fund_postings_operation_id_fund_operations"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_fund_postings")),
        sa.UniqueConstraint(
            "operation_id",
            "account",
            "account_id",
            name=op.f("uq_fund_postings_operation_id_account_account_id"),
        ),
    )
    op.create_index(op.f("ix_fund_postings_account"), "fund_postings", ["account"], unique=False)
    op.create_index(
        op.f("ix_fund_postings_account_id"), "fund_postings", ["account_id"], unique=False
    )
    op.create_index(
        op.f("ix_fund_postings_operation_id"), "fund_postings", ["operation_id"], unique=False
    )
    op.add_column("daily_intervals", sa.Column("efficiency", sa.SmallInteger(), nullable=True))


def downgrade() -> None:
    op.drop_column("daily_intervals", "efficiency")
    op.drop_index(op.f("ix_fund_postings_operation_id"), table_name="fund_postings")
    op.drop_index(op.f("ix_fund_postings_account_id"), table_name="fund_postings")
    op.drop_index(op.f("ix_fund_postings_account"), table_name="fund_postings")
    op.drop_table("fund_postings")
    op.drop_table("fund_reconciliations")
    op.drop_index(op.f("ix_fund_operations_occurred_on"), table_name="fund_operations")
    op.drop_table("fund_operations")
    op.drop_index(op.f("ix_fund_attachments_claim_id"), table_name="fund_attachments")
    op.drop_table("fund_attachments")
    op.drop_table("team_sessions")
    op.drop_table("fund_vacation_years")
    op.drop_index(op.f("ix_fund_time_requests_employee_id"), table_name="fund_time_requests")
    op.drop_table("fund_time_requests")
    op.drop_table("fund_openings")
    op.drop_index(op.f("ix_fund_obligations_month"), table_name="fund_obligations")
    op.drop_index(op.f("ix_fund_obligations_employee_id"), table_name="fund_obligations")
    op.drop_table("fund_obligations")
    op.drop_table("fund_notifications")
    op.drop_index(op.f("ix_fund_loans_employee_id"), table_name="fund_loans")
    op.drop_table("fund_loans")
    op.drop_table("fund_imports")
    op.drop_index(op.f("ix_fund_claims_employee_id"), table_name="fund_claims")
    op.drop_table("fund_claims")
    op.drop_table("fund_baskets")
    op.drop_index(op.f("ix_fund_adjustments_employee_id"), table_name="fund_adjustments")
    op.drop_table("fund_adjustments")
    op.drop_table("team_logins")
