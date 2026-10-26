"""События для realtime (ADR 0003): ``pg_notify`` в той же транзакции, что и запись.

Подписчики получают событие только после коммита. Payload маленький: тип, идентификаторы
и короткий текст для уведомления. Данные клиент перезапрашивает сам.
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

CHANNEL = "teamtime_events"
MAX_PAYLOAD = 7900  # предел PostgreSQL — 8000 байт


async def notify(session: AsyncSession, event_type: str, **payload: Any) -> None:
    body = json.dumps({"type": event_type, **payload}, ensure_ascii=False, default=str)
    if len(body.encode()) > MAX_PAYLOAD:
        body = json.dumps({"type": event_type}, ensure_ascii=False)
    await session.execute(
        text("SELECT pg_notify(:channel, :body)"), {"channel": CHANNEL, "body": body}
    )
