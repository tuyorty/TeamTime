"""Журнал правок: кто, когда, что, было → стало, причина."""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from teamtime.db.models import AuditLog


async def record(
    session: AsyncSession,
    *,
    actor: str,
    action: str,
    entity_type: str,
    entity_id: object = "",
    employee_id: int | None = None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    reason: str = "",
) -> AuditLog:
    entry = AuditLog(
        actor=actor,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id),
        employee_id=employee_id,
        before=before,
        after=after,
        reason=reason,
    )
    session.add(entry)
    await session.flush()
    return entry
