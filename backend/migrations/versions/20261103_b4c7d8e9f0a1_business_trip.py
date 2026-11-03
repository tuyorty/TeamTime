"""Статус дня «Командировка».

Revision ID: b4c7d8e9f0a1
Revises: a3b6c7d8e9f0
"""

from collections.abc import Sequence

from alembic import op

revision: str = "b4c7d8e9f0a1"
down_revision: str | None = "a3b6c7d8e9f0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TYPE status_kind ADD VALUE IF NOT EXISTS 'business_trip'")


def downgrade() -> None:
    # PostgreSQL не удаляет значение enum. Сохраняем его и историю статусов;
    # для отката приложения с командировками требуется восстановление резервной копии.
    pass
