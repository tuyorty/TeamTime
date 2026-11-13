"""Заявки на личные расходы и учётные статусы; утверждает именной руководитель."""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from teamtime.calc.day import FactInput
from teamtime.calc.fund import month_start, next_month
from teamtime.core import clock
from teamtime.db.fund import FundCalendar, FundPeriod
from teamtime.db.fund_operations import (
    FundClaim,
    FundObligation,
    FundTimeRequest,
    FundVacationYear,
)
from teamtime.fund_schemas import ClaimInput, DecisionInput, TimeRequestInput, VacationYearInput
from teamtime.services import facts, manual
from teamtime.services.fund import FundError, lock, member, period, valid_month
from teamtime.services.fund_ledger import audit, internal_operation
from teamtime.services.settings import load_settings


async def open_month(session: AsyncSession, month: date) -> date:
    while (await period(session, month)).closed_at:
        month = next_month(month)
    return month


async def new_claim(session: AsyncSession, actor: int, body: ClaimInput) -> FundClaim:
    await lock(session)
    await member(session, actor)
    valid_month(body.month)
    today = clock.now().astimezone((await load_settings(session)).tz).date()
    if body.spent_on > today:
        raise FundError("Расход ещё не совершён", 422)
    old = await session.scalar(
        select(FundClaim).where(FundClaim.request_id == str(body.request_id))
    )
    if old:
        if old.employee_id != actor or any(
            getattr(old, k) != v for k, v in body.model_dump(exclude={"request_id"}).items()
        ):
            raise FundError("Этот расход уже записан с другими данными")
        return old
    row = FundClaim(
        **body.model_dump(exclude={"request_id"}),
        request_id=str(body.request_id),
        employee_id=actor,
    )
    session.add(row)
    await session.flush()
    audit(session, actor, "claim.created", id=row.id, amount=str(row.amount), title=row.title)
    return row


async def decide_claim(
    session: AsyncSession, actor: int, claim_id: int, body: DecisionInput
) -> FundClaim:
    await lock(session)
    await member(session, actor, leader=True)
    row = await session.get(FundClaim, claim_id, populate_existing=True)
    if row is None:
        raise FundError("Заявка не найдена", 404)
    state = "approved" if body.approve else "rejected"
    if row.state != "pending":
        if row.state == state:
            return row
        raise FundError("По заявке уже принято решение")
    row.state, row.decided_by, row.decided_at = state, actor, clock.now()
    row.decision_reason = body.reason
    if body.approve:
        month = await open_month(session, row.month)
        obligation = FundObligation(
            employee_id=row.employee_id,
            month=month,
            kind="compensation",
            amount=row.amount,
            origin=f"claim:{row.id}",
            title=row.title,
        )
        session.add(obligation)
        await session.flush()
        await internal_operation(
            session,
            actor,
            key=f"claim:{row.id}",
            kind="obligation",
            day=clock.now().astimezone((await load_settings(session)).tz).date(),
            reason=body.reason,
            details={"claim_id": row.id, "month": str(month)},
            entries=[("obligation", obligation.id, row.amount)],
        )
    audit(session, actor, f"claim.{state}", id=row.id, reason=body.reason)
    return row


async def holiday_dates(session: AsyncSession, days: set[date]) -> set[date]:
    holidays: set[date] = set()
    for month in {month_start(day) for day in days}:
        row = await session.scalar(
            select(FundCalendar)
            .where(FundCalendar.month == month)
            .order_by(FundCalendar.version.desc())
            .limit(1)
        )
        if row is None:
            raise FundError(f"Для отпуска нужен утверждённый календарь на {month:%m.%Y}")
        holidays.update(date.fromisoformat(d) for d in row.holidays)
    return holidays


async def vacation_balance(
    session: AsyncSession, employee: int, *, include: set[date] | None = None
) -> list[dict[str, Any]]:
    years = list(
        await session.scalars(
            select(FundVacationYear)
            .where(FundVacationYear.employee_id == employee)
            .order_by(FundVacationYear.start)
        )
    )
    requests = list(
        await session.scalars(
            select(FundTimeRequest).where(
                FundTimeRequest.employee_id == employee,
                FundTimeRequest.kind == "vacation",
                FundTimeRequest.state == "approved",
            )
        )
    )
    days = {date.fromisoformat(d) for r in requests for d in r.days} | (include or set())
    holidays = await holiday_dates(session, days) if days else set()
    today = clock.now().astimezone((await load_settings(session)).tz).date()
    output = []
    for year in years:
        covered = {d for d in days if year.as_of <= d <= year.end} - holidays
        used, future = sum(d < today for d in covered), sum(d >= today for d in covered)
        available = year.opening_days + year.adjustment_days - used - future
        output.append(
            {
                "id": year.id,
                "start": str(year.start),
                "end": str(year.end),
                "as_of": str(year.as_of),
                "annual_days": year.annual_days,
                "opening_days": year.opening_days,
                "adjustment_days": year.adjustment_days,
                "used": used,
                "reserved": future,
                "available": available,
            }
        )
    if include and any(not any(y.as_of <= d <= y.end for y in years) for d in include):
        raise FundError("Для этих дат не задан подтверждённый отпускной год и остаток")
    return output


async def set_vacation_year(
    session: AsyncSession, actor: int, body: VacationYearInput
) -> FundVacationYear:
    await lock(session)
    await member(session, actor, leader=True)
    await member(session, body.employee_id)
    if not body.start <= body.as_of <= body.end:
        raise FundError("Проверьте границы отпускного года и дату остатка", 422)
    old = await session.scalar(
        select(FundVacationYear).where(
            FundVacationYear.employee_id == body.employee_id,
            FundVacationYear.start <= body.end,
            FundVacationYear.end >= body.start,
        )
    )
    if old:
        raise FundError(
            "Год уже задан или пересекается с существующим; изменение оформляется отдельно"
        )
    row = FundVacationYear(**body.model_dump(), approved_by=actor)
    session.add(row)
    await session.flush()
    audit(
        session,
        actor,
        "vacation.opening",
        id=row.id,
        employee_id=body.employee_id,
        days=body.opening_days,
        reason=body.reason,
    )
    return row


def evidence(cell: facts.DayCell) -> dict[str, Any]:
    return {
        "plan_id": cell.plan.id if cell.plan else None,
        "plan_day_id": cell.plan_day.id if cell.plan_day else None,
        "daily_id": cell.daily.id if cell.daily else None,
    }


def raw_late(cell: facts.DayCell, tolerance_sec: int) -> int:
    if not cell.daily or not cell.daily.intervals or not cell.plan_day:
        return 0
    plan = facts.plan_input(cell.plan_day)
    if not plan.has_time or plan.start is None:
        return 0
    fact: FactInput = facts.fact_input(cell.daily)
    late = max(0, fact.arrival_for(plan) - plan.start)
    return late if late > tolerance_sec else 0


async def new_time_request(
    session: AsyncSession, actor: int, employee: int, body: TimeRequestInput
) -> FundTimeRequest:
    await lock(session)
    await member(session, actor, leader=actor != employee)
    await member(session, employee)
    valid_month(month_start(body.days[0]))
    if body.kind in {"missed", "waiver", "no_work"} and len(body.days) != 1:
        raise FundError("Это решение относится к одному конкретному дню", 422)
    if body.kind != "waiver" and body.seconds:
        raise FundError("Длительность вручную задаётся только для исключения опоздания", 422)
    old = await session.scalar(
        select(FundTimeRequest).where(FundTimeRequest.request_id == str(body.request_id))
    )
    if old:
        if (
            old.employee_id != employee
            or old.kind != body.kind
            or old.days != [str(d) for d in body.days]
            or old.seconds != body.seconds
            or old.reason != body.reason
        ):
            raise FundError("Заявка уже сохранена с другими данными")
        return old
    row = FundTimeRequest(
        request_id=str(body.request_id),
        employee_id=employee,
        kind=body.kind,
        days=[str(d) for d in body.days],
        seconds=body.seconds,
        reason=body.reason,
    )
    session.add(row)
    await session.flush()
    audit(
        session,
        actor,
        "time.requested",
        id=row.id,
        employee_id=employee,
        kind=row.kind,
        days=row.days,
    )
    return row


async def decide_time_request(
    session: AsyncSession, actor: int, request_id: int, body: DecisionInput
) -> FundTimeRequest:
    await lock(session)
    await member(session, actor, leader=True)
    row = await session.get(FundTimeRequest, request_id, populate_existing=True)
    if row is None:
        raise FundError("Заявка не найдена", 404)
    state = "approved" if body.approve else "rejected"
    if row.state != "pending":
        if row.state == state:
            return row
        raise FundError("По заявке уже принято другое решение")
    days = {date.fromisoformat(d) for d in row.days}
    if body.approve:
        if row.kind in {"missed", "no_work"}:
            today = clock.now().astimezone((await load_settings(session)).tz).date()
            if any(d >= today for d in days):
                raise FundError(
                    "Факт пропуска или дня без работы подтверждается после окончания дня"
                )
        for month in {month_start(d) for d in days}:
            if (await period(session, month)).closed_at:
                raise FundError("Статус затрагивает закрытый месяц; нужна корректировка")
        others = await session.scalars(
            select(FundTimeRequest).where(
                FundTimeRequest.employee_id == row.employee_id,
                FundTimeRequest.state == "approved",
            )
        )
        for other in others:
            overlap = days & {date.fromisoformat(d) for d in other.days}
            if overlap and (
                other.kind == row.kind or {other.kind, row.kind} != {"waiver", "missed"}
            ):
                raise FundError("Даты пересекаются с согласованным статусом; сначала уточните его")
        settings = await load_settings(session)
        cells = await facts.load_cells(session, settings, min(days), max(days), [row.employee_id])
        proof = {str(d): evidence(cells[row.employee_id, d]) for d in days}
        if row.kind in {"vacation", "sick", "trip", "missed", "no_work"} and any(
            cells[row.employee_id, d].daily for d in days
        ):
            raise FundError("На эти даты есть дейлик; сначала устраните конфликт факта и статуса")
        if row.kind == "vacation":
            balances = await vacation_balance(session, row.employee_id, include=days)
            if any(item["available"] < 0 for item in balances):
                raise FundError(
                    "Не хватает отпускных дней; нужно отдельное решение о статусе отсутствия"
                )
        if row.kind == "missed":
            cell = cells[row.employee_id, min(days)]
            if not cell.plan_day or not facts.plan_input(cell.plan_day).has_time:
                raise FundError("Для полного пропуска нужно подтверждённое расписание со временем")
            row.seconds = facts.plan_input(cell.plan_day).planned_seconds or 0
        if row.kind == "waiver":
            cell = cells[row.employee_id, min(days)]
            late = raw_late(cell, settings.late_tolerance_min * 60)
            missed = await session.scalars(
                select(FundTimeRequest).where(
                    FundTimeRequest.employee_id == row.employee_id,
                    FundTimeRequest.kind == "missed",
                    FundTimeRequest.state == "approved",
                )
            )
            late += sum(r.seconds for r in missed if str(min(days)) in r.days)
            if not 0 < row.seconds <= late:
                raise FundError("Исключаемое время должно быть положительным и не больше исходного")
        row.evidence = proof
        from teamtime.calc.day import StatusKind

        kinds = {
            "vacation": StatusKind.VACATION,
            "sick": StatusKind.SICK,
            "trip": StatusKind.BUSINESS_TRIP,
        }
        if row.kind in kinds:
            for d in sorted(days):
                await manual.set_status(
                    session,
                    employee_id=row.employee_id,
                    day=d,
                    kind=kinds[row.kind],
                    note="",
                    actor=f"fund:{actor}",
                    reason=f"Заявка фонда #{row.id}",
                )
    row.state, row.decided_by, row.decided_at, row.decision_reason = (
        state,
        actor,
        clock.now(),
        body.reason,
    )
    audit(
        session, actor, f"time.{state}", id=row.id, employee_id=row.employee_id, reason=body.reason
    )
    return row


async def cancel_time_request(
    session: AsyncSession, actor: int, request_id: int, reason: str
) -> FundTimeRequest:
    await lock(session)
    await member(session, actor, leader=True)
    row = await session.get(FundTimeRequest, request_id, populate_existing=True)
    if row is None:
        raise FundError("Заявка не найдена", 404)
    if row.state == "cancelled":
        return row
    days = [date.fromisoformat(d) for d in row.days]
    for month in {month_start(d) for d in days}:
        closed = await session.get(FundPeriod, month)
        if closed and closed.closed_at:
            raise FundError("Отмена затрагивает закрытый месяц; нужна корректировка")
    if row.state == "approved" and row.kind in {"vacation", "sick", "trip"}:
        from teamtime.db.models import DayStatus

        for status in await session.scalars(
            select(DayStatus).where(
                DayStatus.employee_id == row.employee_id,
                DayStatus.date.in_(days),
                DayStatus.retracted_at.is_(None),
            )
        ):
            if status.created_by.startswith("fund:"):
                status.retracted_at = clock.now()
    row.state = "cancelled"
    audit(session, actor, "time.cancelled", id=row.id, reason=reason)
    return row
