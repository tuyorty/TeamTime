"""История условий, заявки и наблюдаемость бота.

Revision ID: f2a5b6c7d8e9
Revises: e1f4a5b6c7d8
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql as pg

revision: str = "f2a5b6c7d8e9"
down_revision: str | None = "e1f4a5b6c7d8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _id() -> sa.Column[int]:
    return sa.Column("id", sa.Integer(), primary_key=True)


def _created() -> sa.Column[object]:
    return sa.Column(
        "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )


def _employee(*, primary: bool = False) -> sa.Column[int]:
    return sa.Column(
        "employee_id",
        sa.Integer(),
        sa.ForeignKey("employees.id", ondelete="CASCADE"),
        nullable=False,
        primary_key=primary,
    )


def upgrade() -> None:
    for name in ("expertise", "help_with"):
        op.add_column(
            "employees", sa.Column(name, sa.String(500), nullable=False, server_default="")
        )
    for name in ("deferred_until", "snooze_until", "followup_attempted_at", "followup_sent_at"):
        op.add_column("daily_reminders", sa.Column(name, sa.DateTime(timezone=True)))
    op.add_column(
        "daily_reminders",
        sa.Column("snooze_used", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.add_column("daily_reminders", sa.Column("error_code", sa.String(80)))
    op.create_table(
        "employee_terms",
        _id(),
        _created(),
        _employee(),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("monthly_norm_minutes", sa.Integer(), nullable=False),
        sa.Column("hourly_rate", sa.Numeric(10, 2), nullable=False),
        sa.Column("created_by", sa.String(100), nullable=False),
        sa.UniqueConstraint("employee_id", "effective_from", name="employee_terms_month"),
        sa.CheckConstraint(
            "monthly_norm_minutes >= 0 AND hourly_rate >= 0", name="terms_non_negative"
        ),
    )
    op.create_table(
        "calculation_versions",
        _id(),
        _created(),
        sa.Column("effective_from", sa.Date(), nullable=False, unique=True),
        sa.Column("value", pg.JSONB(), nullable=False),
        sa.Column("created_by", sa.String(100), nullable=False),
    )
    op.create_table(
        "status_requests",
        _id(),
        _created(),
        _employee(),
        sa.Column("start", sa.Date(), nullable=False),
        sa.Column("end", sa.Date(), nullable=False),
        sa.Column("kind", pg.ENUM(name="status_kind", create_type=False)),
        sa.Column("note", sa.String(500), nullable=False, server_default=""),
        sa.Column("state", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("requested_by", sa.String(100), nullable=False),
        sa.Column("decided_by", sa.String(100)),
        sa.Column("decided_at", sa.DateTime(timezone=True)),
        sa.Column("decision_note", sa.String(500), nullable=False, server_default=""),
        sa.CheckConstraint('"end" >= start', name="status_request_dates"),
        sa.CheckConstraint(
            "state IN ('pending','accepted','rejected')", name="status_request_state"
        ),
    )
    op.create_index("ix_status_requests_state", "status_requests", ["state", "created_at"])
    op.create_table(
        "notification_preferences",
        _employee(primary=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("delay_minutes", sa.Integer()),
        sa.Column("quiet_start", sa.Integer()),
        sa.Column("quiet_end", sa.Integer()),
        sa.CheckConstraint("delay_minutes BETWEEN 1 AND 240", name="notification_delay"),
        sa.CheckConstraint(
            "quiet_start BETWEEN 0 AND 1439 AND quiet_end BETWEEN 0 AND 1439",
            name="notification_quiet",
        ),
    )
    op.create_table(
        "bot_drafts",
        sa.Column("id", sa.String(40), primary_key=True),
        _created(),
        _employee(),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("payload", pg.JSONB(), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True)),
        sa.Column("daily_id", sa.Integer(), sa.ForeignKey("dailies.id", ondelete="SET NULL")),
    )
    op.create_table(
        "system_status",
        sa.Column("service", sa.String(30), primary_key=True),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_success_at", sa.DateTime(timezone=True)),
        sa.Column("last_update_at", sa.DateTime(timezone=True)),
        sa.Column("last_error_at", sa.DateTime(timezone=True)),
        sa.Column("error_code", sa.String(100)),
        sa.Column("details", pg.JSONB(), nullable=False),
    )
    op.create_table(
        "bot_deliveries",
        _id(),
        _created(),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("employee_id", sa.Integer(), sa.ForeignKey("employees.id", ondelete="SET NULL")),
        sa.Column(
            "raw_message_id", sa.Integer(), sa.ForeignKey("raw_messages.id", ondelete="SET NULL")
        ),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("error_code", sa.String(100)),
    )
    op.create_index("ix_bot_deliveries_created", "bot_deliveries", ["created_at"])
    # Старые условия невозможно восстановить из отсутствующих данных: фиксируем исходную базу.
    op.execute(
        "INSERT INTO employee_terms "
        "(employee_id,effective_from,monthly_norm_minutes,hourly_rate,created_by) "
        "SELECT id, DATE '2000-01-01', monthly_norm_minutes,hourly_rate,'migration' FROM employees"
    )
    op.execute(
        "INSERT INTO calculation_versions (effective_from,value,created_by) "
        "SELECT DATE '2000-01-01', value,'migration' FROM app_settings WHERE key='app'"
    )


def downgrade() -> None:
    for name in (
        "bot_deliveries",
        "system_status",
        "bot_drafts",
        "notification_preferences",
        "status_requests",
        "calculation_versions",
        "employee_terms",
    ):
        op.drop_table(name)
    for name in (
        "deferred_until",
        "snooze_until",
        "snooze_used",
        "followup_attempted_at",
        "followup_sent_at",
        "error_code",
    ):
        op.drop_column("daily_reminders", name)
    op.drop_column("employees", "help_with")
    op.drop_column("employees", "expertise")
