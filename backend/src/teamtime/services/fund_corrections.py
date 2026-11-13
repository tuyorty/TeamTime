"""Корректировки — отдельные подтверждённые разницы; закрытый снимок не переписывается."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from teamtime.calc.fund import ZERO, money
from teamtime.core import clock
from teamtime.db.fund import FundMember, FundPeriod, FundReceipt, FundSourceState
from teamtime.db.fund_operations import FundAdjustment, FundObligation
from teamtime.fund_schemas import BonusInput, CorrectionInput, DecisionInput
from teamtime.services.fund import FundError, lock, member, valid_month
from teamtime.services.fund_ledger import audit, balance, digest, internal_operation
from teamtime.services.fund_report import calculate_inputs, collect_inputs
from teamtime.services.fund_requests import open_month


async def bonus(session: AsyncSession, actor: int, body: BonusInput) -> FundAdjustment:
    await lock(session)
    await member(session, actor, leader=True)
    await member(session, body.employee_id)
    valid_month(body.month)
    existing = await session.scalar(
        select(FundAdjustment).where(FundAdjustment.request_id == str(body.request_id))
    )
    if existing:
        if (
            existing.employee_id != body.employee_id
            or existing.amount != body.amount
            or existing.origin_month != body.month
            or existing.kind != "bonus"
        ):
            raise FundError("Премия уже сохранена с другими данными")
        return existing
    stored = await session.get(FundPeriod, body.month)
    if stored and stored.closed_at:
        raise FundError("Премия закрытого месяца оформляется зарплатной корректировкой")
    row = FundAdjustment(
        request_id=str(body.request_id),
        employee_id=body.employee_id,
        kind="bonus",
        origin_month=body.month,
        applied_month=body.month,
        amount=body.amount,
        before={},
        after={},
        reason=body.reason,
        state="approved",
        created_by=actor,
        approved_by=actor,
        approved_at=clock.now(),
    )
    session.add(row)
    await session.flush()
    audit(session, actor, "bonus.approved", id=row.id, amount=str(row.amount), reason=body.reason)
    return row


async def previous(
    session: AsyncSession, employee: int, origin: date, kind: str, reference_id: int | None = None
) -> list[FundAdjustment]:
    rows = list(
        await session.scalars(
            select(FundAdjustment)
            .where(
                FundAdjustment.employee_id == employee,
                FundAdjustment.origin_month == origin,
                FundAdjustment.kind == kind,
                FundAdjustment.state == "approved",
            )
            .order_by(FundAdjustment.id)
        )
    )
    return [r for r in rows if kind != "source" or r.after.get("reference_id") == reference_id]


async def propose(session: AsyncSession, actor: int, body: CorrectionInput) -> FundAdjustment:
    await lock(session)
    await member(session, actor, leader=actor != body.employee_id)
    existing = await session.scalar(
        select(FundAdjustment).where(FundAdjustment.request_id == str(body.request_id))
    )
    if existing:
        if (
            existing.after.get("request_hash") != digest(body.model_dump(mode="json"))
            or existing.created_by != actor
        ):
            raise FundError("Корректировка уже сохранена с другим содержимым")
        return existing
    stored = await session.get(FundPeriod, body.origin_month)
    if body.kind != "source" and (stored is None or not stored.closed_at or not stored.snapshot):
        raise FundError("Корректировка начисления относится к закрытому месяцу")
    old_rows = stored.snapshot.get("rows", []) if stored and stored.snapshot else []
    original = next((r for r in old_rows if r["employee"]["id"] == body.employee_id), None)
    accepted = await previous(
        session, body.employee_id, body.origin_month, body.kind, body.reference_id
    )
    before: dict[str, Any] = {"prior_ids": [r.id for r in accepted]}
    after: dict[str, Any] = {"request_hash": digest(body.model_dump(mode="json"))}
    if body.kind == "salary":
        if not original or not original.get("inputs"):
            raise FundError(
                "Для исторического расчёта нужны подтверждённые исходные данные и его правила"
            )
        data = body.corrected_inputs
        if not data:
            person = await session.get(FundMember, body.employee_id)
            if person is None:
                raise FundError("Участник не найден", 404)
            current, problems, _ = await collect_inputs(session, body.origin_month, person)
            if current is None or problems:
                raise FundError("Исправленные часы ещё требуют уточнения")
            data = {
                **original["inputs"],
                "work": current["work"],
                "lateness": current["lateness"],
                "decisions": current["decisions"],
                "proof": current["proof"],
            }
        if body.corrected_conditions is not None:
            data = {
                **data,
                "conditions": [c.model_dump(mode="json") for c in body.corrected_conditions],
            }
        try:
            _, computed = calculate_inputs(data)
        except (ValueError, KeyError, TypeError) as exc:
            raise FundError("Исправленные данные не позволяют воспроизвести расчёт", 422) from exc
        old = Decimal(original["amounts"]["salary"]) + sum((r.amount for r in accepted), ZERO)
        # Премии не пересоздаются при исправлении часов. Явная новая сумма Z+B требует согласования.
        if body.corrected_amount is not None:
            if body.corrected_amount < 0:
                raise FundError("Начисление не может быть отрицательным", 422)
            computed = body.corrected_amount - Decimal(original["amounts"]["bonus"])
        before["amount"] = str(old)
        after.update({"amount": str(computed), "inputs": data})
    elif body.kind == "source":
        receipt = await session.get(FundReceipt, body.reference_id) if body.reference_id else None
        if (
            receipt is None
            or receipt.employee_id != body.employee_id
            or receipt.origin_month != body.origin_month
        ):
            raise FundError("Укажите исправляемое поступление участника", 422)
        if body.corrected_amount is None or body.corrected_amount < 0:
            raise FundError("Укажите правильную сумму поступления, включая ноль", 422)
        old = receipt.amount + sum((r.amount for r in accepted), ZERO)
        computed = body.corrected_amount
        before.update({"amount": str(old), "reference_id": receipt.id})
        after.update(
            {"amount": str(computed), "reference_id": receipt.id, "source": receipt.source}
        )
    else:
        if original is None or body.corrected_amount is None or body.corrected_amount < 0:
            raise FundError("Укажите новый итог компенсаций закрытого месяца", 422)
        old = Decimal(original["amounts"]["compensation"]) + sum((r.amount for r in accepted), ZERO)
        computed = body.corrected_amount
        before["amount"], after["amount"] = str(old), str(computed)
    difference = money(computed - old)
    if not difference:
        raise FundError("Исправление не меняет денежный результат")
    applied = await open_month(session, body.origin_month)
    row = FundAdjustment(
        request_id=str(body.request_id),
        employee_id=body.employee_id,
        kind=body.kind,
        origin_month=body.origin_month,
        applied_month=applied,
        amount=difference,
        before=before,
        after=after,
        reason=body.reason,
        state="pending",
        created_by=actor,
    )
    session.add(row)
    await session.flush()
    audit(
        session,
        actor,
        "adjustment.proposed",
        id=row.id,
        kind=row.kind,
        origin_month=str(row.origin_month),
        amount=str(row.amount),
        reason=row.reason,
    )
    return row


async def decide(
    session: AsyncSession, actor: int, adjustment_id: int, body: DecisionInput
) -> FundAdjustment:
    await lock(session)
    await member(session, actor, leader=True)
    row = await session.get(FundAdjustment, adjustment_id, populate_existing=True)
    if row is None:
        raise FundError("Корректировка не найдена", 404)
    state = "approved" if body.approve else "rejected"
    if row.state != "pending":
        if row.state == state:
            return row
        raise FundError("Решение уже принято")
    if body.approve:
        accepted = await previous(
            session, row.employee_id, row.origin_month, row.kind, row.after.get("reference_id")
        )
        if [r.id for r in accepted] != row.before.get("prior_ids", []):
            raise FundError("Уже принята другая корректировка; сначала пересчитайте разницу")
        row.applied_month = await open_month(session, row.applied_month)
        if row.kind == "compensation":
            if row.amount > 0:
                obligation = FundObligation(
                    employee_id=row.employee_id,
                    month=row.applied_month,
                    kind="compensation",
                    amount=row.amount,
                    origin=f"adjustment:{row.id}",
                    title=f"Корректировка компенсации за {row.origin_month:%m.%Y}",
                )
                session.add(obligation)
                await session.flush()
                await internal_operation(
                    session,
                    actor,
                    key=f"adjustment:{row.id}",
                    kind="obligation",
                    day=row.applied_month,
                    reason=body.reason,
                    details={"adjustment_id": row.id},
                    entries=[("obligation", obligation.id, row.amount)],
                )
            else:
                outstanding = []
                for obligation in await session.scalars(
                    select(FundObligation)
                    .where(
                        FundObligation.employee_id == row.employee_id,
                        FundObligation.month == row.origin_month,
                        FundObligation.kind == "compensation",
                    )
                    .order_by(FundObligation.id)
                ):
                    outstanding.append(
                        (
                            obligation.id,
                            max(ZERO, await balance(session, "obligation", obligation.id)),
                        )
                    )
                remaining = -row.amount
                entries = []
                for oid, amount in outstanding:
                    part = min(remaining, amount)
                    entries.append(("obligation", oid, -part))
                    remaining -= part
                if remaining:
                    # Выплаченная компенсация не становится зарплатной переплатой.
                    # Отрицательный остаток остаётся отдельным требованием до решения о возврате.
                    credit = FundObligation(
                        employee_id=row.employee_id,
                        month=row.applied_month,
                        kind="compensation",
                        amount=ZERO,
                        origin=f"adjustment:{row.id}",
                        title=f"Уменьшение выплаченной компенсации за {row.origin_month:%m.%Y}",
                    )
                    session.add(credit)
                    await session.flush()
                    entries.append(("obligation", credit.id, -remaining))
                await internal_operation(
                    session,
                    actor,
                    key=f"adjustment:{row.id}",
                    kind="compensation_correction",
                    day=row.applied_month,
                    reason=body.reason,
                    details={"adjustment_id": row.id},
                    entries=entries,
                )
        if row.kind == "source":
            source = row.after["source"]
            completion = await session.get(
                FundSourceState, (row.employee_id, row.applied_month, source)
            )
            if completion:
                completion.complete = False
                completion.version += 1
                completion.changed_by, completion.updated_at = actor, clock.now()
        row.approved_by, row.approved_at = actor, clock.now()
    row.state = state
    audit(
        session,
        actor,
        f"adjustment.{state}",
        id=row.id,
        kind=row.kind,
        amount=str(row.amount),
        applied_month=str(row.applied_month),
        reason=body.reason,
    )
    await session.flush()
    return row
