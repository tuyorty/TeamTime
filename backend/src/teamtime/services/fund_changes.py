"""Правки рабочих исходников закрытого месяца требуют отдельной проверки руководителем."""

from datetime import date, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from teamtime.calc.fund import month_start
from teamtime.db.fund import FundAudit, FundMember, FundPeriod
from teamtime.services.fund import FundError, lock, member


async def changed(session: AsyncSession, event: str, payload: dict[str, Any]) -> None:
    employee = payload.get("employee_id")
    if (
        not employee
        or not payload.get("dates")
        or event not in {"daily.changed", "plan.changed", "status.changed", "message.ingested"}
    ):
        return
    if await session.get(FundMember, employee) is None:
        return
    months = {
        month_start(date.fromisoformat(d) + timedelta(days=offset))
        for d in payload["dates"]
        for offset in (0, 1)
    }
    for month in months:
        period = await session.get(FundPeriod, month)
        if (
            period
            and period.closed_at
            and (period.snapshot or {}).get("ruleset") != "historical-confirmed"
        ):
            session.add(
                FundAudit(
                    actor_id=employee,
                    action="closed_time.changed",
                    data={
                        "employee_id": employee,
                        "month": str(month),
                        "trigger": event,
                        "source_actor": payload.get("actor", "Telegram"),
                    },
                )
            )


async def pending(session: AsyncSession) -> list[dict[str, Any]]:
    changed_rows: dict[tuple[int, str], FundAudit] = {}
    reviewed: set[int] = set()
    for event in await session.scalars(
        select(FundAudit)
        .where(FundAudit.action.in_(["closed_time.changed", "closed_time.reviewed"]))
        .order_by(FundAudit.id)
    ):
        if event.action == "closed_time.changed":
            changed_rows[event.data["employee_id"], event.data["month"]] = event
        else:
            reviewed.add(event.data["event_id"])
    return [
        {
            "event_id": e.id,
            "employee_id": e.data["employee_id"],
            "month": e.data["month"],
            "created_at": e.created_at,
        }
        for e in changed_rows.values()
        if e.id not in reviewed
    ]


async def reviewed(session: AsyncSession, actor: int, event_id: int, reason: str) -> None:
    await lock(session)
    await member(session, actor, leader=True)
    event = await session.get(FundAudit, event_id)
    if event is None or event.action != "closed_time.changed":
        raise FundError("Изменение закрытого месяца не найдено", 404)
    if not any(p["event_id"] == event_id for p in await pending(session)):
        raise FundError("Исходники изменились снова или проверка уже выполнена; обновите список")
    session.add(
        FundAudit(
            actor_id=actor,
            action="closed_time.reviewed",
            data={"event_id": event_id, "reason": reason},
        )
    )
