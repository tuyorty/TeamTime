"""Версии календаря и условий, поступления и подтверждение их полноты.

Revision ID: e7f0a1b2c3d4
Revises: d6e9f0a1b2c3
Create Date: 2026-11-05 14:45:00.096718+00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "e7f0a1b2c3d4"
down_revision: str | None = "d6e9f0a1b2c3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "fund_members",
        sa.Column("employee_id", sa.Integer(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("leader", sa.Boolean(), nullable=False),
        sa.Column("joined_on", sa.Date(), nullable=False),
        sa.Column("left_on", sa.Date(), nullable=True),
        sa.Column("appointed_by", sa.String(length=100), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "left_on IS NULL OR left_on >= joined_on", name=op.f("ck_fund_members_dates")
        ),
        sa.ForeignKeyConstraint(
            ["employee_id"], ["employees.id"], name=op.f("fk_fund_members_employee_id_employees")
        ),
        sa.PrimaryKeyConstraint("employee_id", name=op.f("pk_fund_members")),
    )
    op.create_table(
        "fund_audit",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("actor_id", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(length=80), nullable=False),
        sa.Column("data", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["actor_id"],
            ["fund_members.employee_id"],
            name=op.f("fk_fund_audit_actor_id_fund_members"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_fund_audit")),
    )
    op.create_table(
        "fund_calendars",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("month", sa.Date(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("source_version", sa.String(length=100), nullable=False),
        sa.Column("days", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("holidays", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "EXTRACT(DAY FROM month) = 1 AND version >= 1",
            name=op.f("ck_fund_calendars_month_version"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["fund_members.employee_id"],
            name=op.f("fk_fund_calendars_created_by_fund_members"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_fund_calendars")),
        sa.UniqueConstraint("month", "version", name=op.f("uq_fund_calendars_month_version")),
    )
    op.create_index(op.f("ix_fund_calendars_month"), "fund_calendars", ["month"], unique=False)
    op.create_table(
        "fund_periods",
        sa.Column("month", sa.Date(), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_by", sa.Integer(), nullable=True),
        sa.Column("snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "(closed_at IS NULL AND closed_by IS NULL AND snapshot IS NULL) OR "
            "(closed_at IS NOT NULL AND closed_by IS NOT NULL AND snapshot IS NOT NULL)",
            name=op.f("ck_fund_periods_closure"),
        ),
        sa.CheckConstraint("EXTRACT(DAY FROM month) = 1", name=op.f("ck_fund_periods_month")),
        sa.ForeignKeyConstraint(
            ["closed_by"],
            ["fund_members.employee_id"],
            name=op.f("fk_fund_periods_closed_by_fund_members"),
        ),
        sa.PrimaryKeyConstraint("month", name=op.f("pk_fund_periods")),
    )
    op.create_table(
        "fund_terms",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("employee_id", sa.Integer(), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("target", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("share", sa.Numeric(precision=8, scale=4), nullable=False),
        sa.Column("sources", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("no_other_income", sa.Boolean(), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "target >= 0 AND share > 0 AND revision >= 1", name=op.f("ck_fund_terms_values")
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["fund_members.employee_id"],
            name=op.f("fk_fund_terms_created_by_fund_members"),
        ),
        sa.ForeignKeyConstraint(
            ["employee_id"],
            ["fund_members.employee_id"],
            name=op.f("fk_fund_terms_employee_id_fund_members"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_fund_terms")),
        sa.UniqueConstraint(
            "employee_id",
            "effective_from",
            "revision",
            name=op.f("uq_fund_terms_employee_id_effective_from_revision"),
        ),
    )
    op.create_index(op.f("ix_fund_terms_employee_id"), "fund_terms", ["employee_id"], unique=False)
    op.create_table(
        "fund_receipts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("request_id", sa.String(length=36), nullable=False),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("employee_id", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=100), nullable=False),
        sa.Column("origin_month", sa.Date(), nullable=False),
        sa.Column("applied_month", sa.Date(), nullable=False),
        sa.Column("received_on", sa.Date(), nullable=False),
        sa.Column("amount", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "EXTRACT(DAY FROM origin_month) = 1", name=op.f("ck_fund_receipts_origin_month")
        ),
        sa.CheckConstraint("amount > 0", name=op.f("ck_fund_receipts_positive")),
        sa.ForeignKeyConstraint(
            ["applied_month"],
            ["fund_periods.month"],
            name=op.f("fk_fund_receipts_applied_month_fund_periods"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by"],
            ["fund_members.employee_id"],
            name=op.f("fk_fund_receipts_created_by_fund_members"),
        ),
        sa.ForeignKeyConstraint(
            ["employee_id"],
            ["fund_members.employee_id"],
            name=op.f("fk_fund_receipts_employee_id_fund_members"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_fund_receipts")),
        sa.UniqueConstraint("request_id", name=op.f("uq_fund_receipts_request_id")),
    )
    op.create_index(
        op.f("ix_fund_receipts_employee_id"), "fund_receipts", ["employee_id"], unique=False
    )
    op.create_table(
        "fund_source_states",
        sa.Column("employee_id", sa.Integer(), nullable=False),
        sa.Column("month", sa.Date(), nullable=False),
        sa.Column("source", sa.String(length=100), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("complete", sa.Boolean(), nullable=False),
        sa.Column("confirmed_total", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("changed_by", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "version >= 1 AND confirmed_total >= 0", name=op.f("ck_fund_source_states_values")
        ),
        sa.ForeignKeyConstraint(
            ["changed_by"],
            ["fund_members.employee_id"],
            name=op.f("fk_fund_source_states_changed_by_fund_members"),
        ),
        sa.ForeignKeyConstraint(
            ["employee_id"],
            ["fund_members.employee_id"],
            name=op.f("fk_fund_source_states_employee_id_fund_members"),
        ),
        sa.ForeignKeyConstraint(
            ["month"], ["fund_periods.month"], name=op.f("fk_fund_source_states_month_fund_periods")
        ),
        sa.PrimaryKeyConstraint(
            "employee_id", "month", "source", name=op.f("pk_fund_source_states")
        ),
    )


def downgrade() -> None:
    op.drop_table("fund_source_states")
    op.drop_index(op.f("ix_fund_receipts_employee_id"), table_name="fund_receipts")
    op.drop_table("fund_receipts")
    op.drop_index(op.f("ix_fund_terms_employee_id"), table_name="fund_terms")
    op.drop_table("fund_terms")
    op.drop_table("fund_periods")
    op.drop_index(op.f("ix_fund_calendars_month"), table_name="fund_calendars")
    op.drop_table("fund_calendars")
    op.drop_table("fund_audit")
    op.drop_table("fund_members")
