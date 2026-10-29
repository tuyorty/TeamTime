"""Контакты, фотография и описание сотрудника.

Revision ID: c8d2e3f4a5b6
Revises: b7c1d2e3f4a5
Create Date: 2026-10-29
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c8d2e3f4a5b6"
down_revision: str | None = "b7c1d2e3f4a5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for name, column_type in (
        ("phone", sa.String(40)),
        ("about", sa.String(500)),
        ("avatar_url", sa.Text()),
    ):
        op.add_column(
            "employees",
            sa.Column(name, column_type, nullable=False, server_default=""),
        )


def downgrade() -> None:
    for name in ("avatar_url", "about", "phone"):
        op.drop_column("employees", name)
