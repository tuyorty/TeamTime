"""Разрешить подписанный итог источника при позднем исправлении прошлой выплаты.

Revision ID: a9b2c3d4e5f6
Revises: f8a1b2c3d4e5
"""

from alembic import op

revision = "a9b2c3d4e5f6"
down_revision = "f8a1b2c3d4e5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint(op.f("ck_fund_source_states_values"), "fund_source_states", type_="check")
    op.create_check_constraint(
        op.f("ck_fund_source_states_values"), "fund_source_states", "version >= 1"
    )
    op.create_check_constraint(
        op.f("ck_daily_intervals_efficiency"),
        "daily_intervals",
        "efficiency IS NULL OR (efficiency >= 0 AND efficiency <= 100)",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("ck_daily_intervals_efficiency"), "daily_intervals", type_="check")
    op.drop_constraint(op.f("ck_fund_source_states_values"), "fund_source_states", type_="check")
    op.create_check_constraint(
        op.f("ck_fund_source_states_values"),
        "fund_source_states",
        "version >= 1 AND confirmed_total >= 0",
    )
