"""Ручные премии к месячному расчёту оплаты.

Revision ID: a3b6c7d8e9f0
Revises: f2a5b6c7d8e9
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a3b6c7d8e9f0"
down_revision: str | None = "f2a5b6c7d8e9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "project_bonuses",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("request_id", sa.String(36), nullable=False, unique=True),
        sa.Column(
            "employee_id",
            sa.Integer(),
            sa.ForeignKey("employees.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("month", sa.Date(), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("note", sa.String(1000), nullable=False, server_default=""),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_by", sa.String(100), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column("cancelled_at", sa.DateTime(timezone=True)),
        sa.Column("cancel_reason", sa.String(500), nullable=False, server_default=""),
        sa.CheckConstraint("amount > 0 AND amount <= 1000000000", name="bonus_amount"),
        sa.CheckConstraint(
            "EXTRACT(DAY FROM month) = 1 AND month BETWEEN '2000-01-01' AND '2100-12-01'",
            name="bonus_month",
        ),
    )
    op.create_index(
        "ix_project_bonuses_month_employee", "project_bonuses", ["month", "employee_id"]
    )


def downgrade() -> None:
    op.drop_table("project_bonuses")
