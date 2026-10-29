"""Фиксация попытки до отправки: неопределённый результат не вызывает повтор.

Revision ID: e1f4a5b6c7d8
Revises: d9e3f4a5b6c7
Create Date: 2026-10-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e1f4a5b6c7d8"
down_revision: str | None = "d9e3f4a5b6c7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("daily_reminders", sa.Column("attempted_at", sa.DateTime(timezone=True)))
    op.add_column(
        "daily_reminders",
        sa.Column("attempts", sa.SmallInteger(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("daily_reminders", "attempts")
    op.drop_column("daily_reminders", "attempted_at")
