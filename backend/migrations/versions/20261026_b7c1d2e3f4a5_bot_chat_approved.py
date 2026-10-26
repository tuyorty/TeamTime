"""bot_chats.approved: сообщения принимаются только из разрешённых админом чатов

Revision ID: b7c1d2e3f4a5
Revises: feca34eec49d
Create Date: 2026-10-26 17:00:00+00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b7c1d2e3f4a5"
down_revision: str | None = "feca34eec49d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "bot_chats",
        sa.Column(
            "approved",
            sa.Boolean(),
            server_default="false",
            nullable=False,
            comment="Разрешён админом на сайте. Сообщения из неразрешённых чатов бот не принимает",
        ),
    )
    # Чаты, которые уже есть, привязаны до этой проверки — оставляем их рабочими.
    op.execute("UPDATE bot_chats SET approved = true")


def downgrade() -> None:
    op.drop_column("bot_chats", "approved")
