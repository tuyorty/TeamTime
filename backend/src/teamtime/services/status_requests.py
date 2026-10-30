"""Сотрудник запрашивает изменение, администратор применяет его одной транзакцией."""

from __future__ import annotations

from datetime import date

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from teamtime.calc import StatusKind
from teamtime.core import clock
from teamtime.db.models import Employee, StatusRequest
from teamtime.services import audit, events, manual


async def request_status(
    session: AsyncSession,
    employee: Employee,
    start: date,
    end: date,
    kind: StatusKind | None,
    actor: str,
    note: str = "",
) -> StatusRequest:
    if not employee.is_active:
        raise manual.EditError("Сотрудник неактивен")
    if end < start or (end - start).days > 62:
        raise manual.EditError("Укажите период от 1 до 63 дней")
    await session.execute(
        text("SELECT pg_advisory_xact_lock(:employee, 21332)"), {"employee": employee.id}
    )
    pending = await session.scalar(
        select(StatusRequest)
        .where(
            StatusRequest.employee_id == employee.id,
            StatusRequest.state == "pending",
            StatusRequest.start <= end,
            StatusRequest.end >= start,
        )
        .with_for_update()
    )
    if pending:
        if (
            pending.start == start
            and pending.end == end
            and pending.kind == kind
            and pending.note == note
        ):
            return pending
        raise manual.EditError("На эти дни уже есть заявка. Дождитесь решения или отзовите её.")
    row = StatusRequest(
        employee_id=employee.id,
        start=start,
        end=end,
        kind=kind,
        requested_by=actor,
        note=note[:500],
        state="pending",
    )
    session.add(row)
    await session.flush()
    await audit.record(
        session,
        actor=actor,
        action="status.request",
        entity_type="status_request",
        entity_id=row.id,
        employee_id=employee.id,
        after={
            "start": start.isoformat(),
            "end": end.isoformat(),
            "kind": kind.value if kind else None,
            "note": note,
        },
    )
    await events.notify(session, "status_request.changed", employee_id=employee.id)
    return row


async def decide(
    session: AsyncSession,
    request_id: int,
    accepted: bool,
    actor: str,
    note: str = "",
) -> StatusRequest:
    row = await session.scalar(
        select(StatusRequest).where(StatusRequest.id == request_id).with_for_update()
    )
    if row is None:
        raise manual.EditError("Заявка не найдена")
    decision = "accepted" if accepted else "rejected"
    if row.state != "pending":
        if row.state == decision:
            return row
        raise manual.EditError("По этой заявке уже принято другое решение")
    if accepted:
        await manual.set_status_range(
            session,
            employee_id=row.employee_id,
            start=row.start,
            end=row.end,
            kind=row.kind,
            note=row.note,
            actor=actor,
            reason=f"Одобрена заявка #{row.id}",
        )
    row.state, row.decided_by, row.decided_at = decision, actor, clock.now()
    row.decision_note = note[:500]
    await audit.record(
        session,
        actor=actor,
        action=f"status_request.{decision}",
        entity_type="status_request",
        entity_id=row.id,
        employee_id=row.employee_id,
        before={"state": "pending"},
        after={"state": decision},
        reason=note,
    )
    await events.notify(session, "status_request.changed", employee_id=row.employee_id)
    return row


async def withdraw(
    session: AsyncSession, request_id: int, employee_id: int, actor: str
) -> StatusRequest:
    row = await session.scalar(
        select(StatusRequest).where(StatusRequest.id == request_id).with_for_update()
    )
    if row is None or row.employee_id != employee_id:
        raise manual.EditError("Заявка не найдена")
    return await decide(session, request_id, False, actor, "Отозвана сотрудником")
