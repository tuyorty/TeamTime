from __future__ import annotations

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from teamtime.db.models import Employee, ParseResultRow, RawMessage, Resolution
from teamtime.demo.seed import seed_demo
from teamtime.services import reports
from teamtime.services.settings import load_settings

pytestmark = pytest.mark.db


async def test_seed_builds_a_believable_demo(session: AsyncSession) -> None:
    assert await seed_demo(session, weeks=4)
    assert await session.scalar(select(func.count()).select_from(Employee)) == 8
    messages = await session.scalar(select(func.count()).select_from(RawMessage)) or 0
    assert messages > 80
    pending = await session.scalar(
        select(func.count())
        .select_from(ParseResultRow)
        .where(ParseResultRow.is_latest, ParseResultRow.resolution == Resolution.PENDING)
    )
    assert pending is not None and 1 <= pending <= 15  # инбокс есть, но не завален
    settings = await load_settings(session)
    week = await reports.week_report(session, settings, 2026, 43)
    assert sum(r.totals.days_worked for r in week.rows) > 25

    # Повторный запуск без --force не трогает данные, с --if-empty — тихо пропускает.
    assert await seed_demo(session, if_empty=True) is False
    with pytest.raises(RuntimeError):
        await seed_demo(session)
