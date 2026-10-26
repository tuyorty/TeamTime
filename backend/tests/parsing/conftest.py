from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest

TZ = ZoneInfo("Asia/Yekaterinburg")
# Суббота, 24.10.2026, 15:00 по Екатеринбургу.
SENT = datetime(2026, 10, 24, 10, 0, tzinfo=UTC)


@pytest.fixture
def tz() -> ZoneInfo:
    return TZ


@pytest.fixture
def sent() -> datetime:
    return SENT


def codes(result: object) -> set[str]:
    return {i.code for i in result.issues}  # type: ignore[attr-defined]
