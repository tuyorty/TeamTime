"""Однократные напоминания перед рабочим днём."""

import sqlalchemy as sa
from alembic import op

revision = "d6e9f0a1b2c3"
down_revision = "c5d8e9f0a1b2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "notification_preferences",
        sa.Column("arrival_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.create_table(
        "shift_reminders",
        sa.Column(
            "employee_id",
            sa.Integer(),
            sa.ForeignKey("employees.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("work_date", sa.Date(), primary_key=True),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("shift_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempted_at", sa.DateTime(timezone=True)),
        sa.Column("sent_at", sa.DateTime(timezone=True)),
        sa.Column("attempts", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True)),
        sa.Column("error_code", sa.String(100)),
    )


def downgrade() -> None:
    op.drop_table("shift_reminders")
    op.drop_column("notification_preferences", "arrival_enabled")
