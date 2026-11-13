"""Подтверждённые невыходы со снимком плановых часов.

Revision ID: b0c3d4e5f6a7
Revises: a9b2c3d4e5f6
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "b0c3d4e5f6a7"
down_revision = "a9b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "day_no_shows",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("employee_id", sa.Integer(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("plan_id", sa.Integer(), nullable=False),
        sa.Column("seconds", sa.Integer(), nullable=False),
        sa.Column("intervals", postgresql.JSONB(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("created_by", sa.String(100), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("retracted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("seconds > 0", name=op.f("ck_day_no_shows_seconds_positive")),
        sa.ForeignKeyConstraint(
            ["employee_id"],
            ["employees.id"],
            name=op.f("fk_day_no_shows_employee_id_employees"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["plan_id"],
            ["schedule_plans.id"],
            name=op.f("fk_day_no_shows_plan_id_schedule_plans"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_day_no_shows")),
    )
    op.create_index(
        "uq_day_no_shows_active",
        "day_no_shows",
        ["employee_id", "date"],
        unique=True,
        postgresql_where=sa.text("retracted_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_day_no_shows_active", table_name="day_no_shows")
    op.drop_table("day_no_shows")
