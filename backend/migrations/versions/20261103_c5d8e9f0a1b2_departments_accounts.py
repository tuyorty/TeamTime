"""Отделы команды и удаление неизвестных Telegram-аккаунтов из списка.

Revision ID: c5d8e9f0a1b2
Revises: b4c7d8e9f0a1
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c5d8e9f0a1b2"
down_revision: str | None = "b4c7d8e9f0a1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "employees",
        sa.Column("department", sa.String(32), nullable=False, server_default="software"),
    )
    op.add_column("bot_chats", sa.Column("department", sa.String(32)))
    op.add_column("telegram_identities", sa.Column("removed_at", sa.DateTime(timezone=True)))
    op.create_check_constraint(
        "employee_department", "employees", "department IN ('software', 'laboratory')"
    )
    op.create_check_constraint(
        "chat_department", "bot_chats", "department IN ('software', 'laboratory')"
    )


def downgrade() -> None:
    op.drop_constraint("chat_department", "bot_chats", type_="check")
    op.drop_constraint("employee_department", "employees", type_="check")
    op.drop_column("telegram_identities", "removed_at")
    op.drop_column("bot_chats", "department")
    op.drop_column("employees", "department")
