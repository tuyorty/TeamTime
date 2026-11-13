"""Журнал фонда. Проведение атомарно; черновики и сверки не меняют деньги."""

from __future__ import annotations

import calendar
import hashlib
import json
from collections import defaultdict
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from teamtime.calc.fund import ZERO, money, month_start, runway
from teamtime.core import clock
from teamtime.db.fund import FundAudit, FundPeriod
from teamtime.db.fund_operations import (
    FundBasket,
    FundLoan,
    FundObligation,
    FundOperation,
    FundPosting,
    FundReconciliation,
)
from teamtime.fund_schemas import LoanInput, OperationInput, ReconciliationInput
from teamtime.services.fund import FundError, lock, member
from teamtime.services.settings import load_settings


def digest(data: Any) -> str:
    return hashlib.sha256(
        json.dumps(data, sort_keys=True, ensure_ascii=False, default=str).encode()
    ).hexdigest()


def audit(session: AsyncSession, actor: int, action: str, **data: Any) -> None:
    session.add(FundAudit(actor_id=actor, action=action, data=data))


async def balance(
    session: AsyncSession, account: str, account_id: int, through: date | None = None
) -> Decimal:
    query = (
        select(func.coalesce(func.sum(FundPosting.amount), 0))
        .join(FundOperation)
        .where(
            FundPosting.account == account,
            FundPosting.account_id == account_id,
            FundOperation.state == "posted",
        )
    )
    if through is not None:
        query = query.where(FundOperation.occurred_on <= through)
    return Decimal(await session.scalar(query) or 0)


async def obligation_paid(session: AsyncSession, obligation_id: int) -> Decimal:
    """Погашение деньгами/зачётом отдельно от уменьшения начисленной компенсации."""
    rows = await session.execute(
        select(FundPosting, FundOperation)
        .join(FundOperation)
        .where(
            FundPosting.account == "obligation",
            FundPosting.account_id == obligation_id,
            FundOperation.state == "posted",
        )
    )
    paid = ZERO
    for posting, operation in rows:
        kind = operation.kind
        if kind == "reversal" and operation.reverses_id:
            original = await session.get(FundOperation, operation.reverses_id)
            kind = original.kind if original else ""
        if kind in {"payment", "allocate", "loan_offset", "import_payment", "compensation_return"}:
            paid -= posting.amount
    return paid


async def post_entries(
    session: AsyncSession,
    operation: FundOperation,
    actor: int,
    entries: list[tuple[str, int, Decimal]],
) -> None:
    totals: dict[tuple[str, int], Decimal] = defaultdict(lambda: ZERO)
    for account, account_id, amount in entries:
        totals[account, account_id] += amount
    # Начальный снимок уже содержит прошлые движения: повторно прибавлять их нельзя.
    if operation.kind != "opening":
        for account, account_id in totals:
            if account != "cash":
                continue
            baseline = await session.scalar(
                select(FundOperation.occurred_on).where(
                    FundOperation.kind == "opening",
                    FundOperation.details["basket_id"].as_integer() == account_id,
                )
            )
            if baseline is not None and operation.occurred_on <= baseline:
                raise FundError(
                    "Дата уже включена в начальный остаток корзины; "
                    "нужна сверка, а не повторное движение"
                )
    for (account, account_id), amount in totals.items():
        if amount:
            session.add(
                FundPosting(
                    operation_id=operation.id,
                    account=account,
                    account_id=account_id,
                    amount=money(amount),
                )
            )
    operation.state = "posted"
    operation.confirmed_by = actor
    operation.confirmed_at = clock.now()
    audit(
        session,
        actor,
        "operation.posted",
        id=operation.id,
        kind=operation.kind,
        amount=str(operation.amount),
        reason=operation.reason,
    )
    await session.flush()


async def internal_operation(
    session: AsyncSession,
    actor: int,
    *,
    key: str,
    kind: str,
    day: date,
    reason: str,
    details: dict[str, Any],
    entries: list[tuple[str, int, Decimal]],
) -> FundOperation:
    """Системная проводка вызывается только после проверки исходной операции сервисом."""
    payload = {
        "key": key,
        "kind": kind,
        "day": str(day),
        "details": details,
        "entries": [(a, i, str(v)) for a, i, v in entries],
    }
    from uuid import NAMESPACE_URL, uuid5

    request_id = str(uuid5(NAMESPACE_URL, f"xtime-fund:{key}"))
    old = await session.scalar(select(FundOperation).where(FundOperation.request_id == request_id))
    if old:
        if old.payload_hash != digest(payload):
            raise FundError("Повторное проведение содержит другие данные")
        return old
    row = FundOperation(
        request_id=request_id,
        payload_hash=digest(payload),
        kind=kind,
        occurred_on=day,
        amount=ZERO,
        details=details,
        reason=reason,
        created_by=actor,
        state="draft",
    )
    session.add(row)
    await session.flush()
    await post_entries(session, row, actor, entries)
    return row


async def basket_owner(session: AsyncSession, actor: int, basket_id: int | None) -> FundBasket:
    await member(session, actor)
    basket = await session.get(FundBasket, basket_id) if basket_id is not None else None
    if basket is None or not basket.active:
        raise FundError("Корзина не найдена", 404)
    if basket.owner_id != actor:
        raise FundError("Подтвердить операцию может только ответственный за эту корзину", 403)
    return basket


async def new_operation(session: AsyncSession, actor: int, body: OperationInput) -> FundOperation:
    await lock(session)
    await member(session, actor)
    today = clock.now().astimezone((await load_settings(session)).tz).date()
    if body.occurred_on > today:
        raise FundError("Будущая дата не является фактом движения денег", 422)
    payload = {**body.model_dump(mode="json"), "author": actor}
    existing = await session.scalar(
        select(FundOperation).where(FundOperation.request_id == str(body.request_id))
    )
    if existing:
        if existing.payload_hash != digest(payload):
            raise FundError("Запрос уже сохранён с другим содержимым")
        return existing
    if body.kind in {"loan_offset", "allocate"}:
        await member(session, actor, leader=True)
        if body.basket_id is not None or body.target_basket_id is not None:
            raise FundError("Неденежный зачёт не использует корзину", 422)
    else:
        await basket_owner(session, actor, body.basket_id)
    if body.target_basket_id is not None:
        target = await session.get(FundBasket, body.target_basket_id)
        if (
            body.kind != "transfer"
            or target is None
            or not target.active
            or target.id == body.basket_id
        ):
            raise FundError("Для перевода нужны две разные действующие корзины", 422)
    if body.kind == "transfer" and body.target_basket_id is None:
        raise FundError("Выберите корзину назначения", 422)
    if body.employee_id is not None:
        # Историческое обязательство можно выплатить уже ушедшему сотруднику.
        from teamtime.db.fund import FundMember

        if await session.get(FundMember, body.employee_id) is None:
            raise FundError("Участник не найден", 404)
    if (
        body.kind
        in {
            "payment",
            "loan_issue",
            "loan_repayment",
            "loan_offset",
            "overpayment_return",
            "allocate",
            "compensation_return",
        }
        and not body.employee_id
    ):
        raise FundError("Укажите участника", 422)
    details = body.model_dump(
        mode="json", include={"allocations", "loan_id", "original_id", "correction_direction"}
    )
    row = FundOperation(
        request_id=str(body.request_id),
        payload_hash=digest(payload),
        kind=body.kind,
        occurred_on=body.occurred_on,
        amount=body.amount,
        basket_id=body.basket_id,
        target_basket_id=body.target_basket_id,
        employee_id=body.employee_id,
        details=details,
        reason=body.reason,
        created_by=actor,
        state="draft",
    )
    session.add(row)
    await session.flush()
    audit(session, actor, "operation.draft", id=row.id, kind=row.kind)
    return row


async def consent(session: AsyncSession, actor: int, operation_id: int) -> FundOperation:
    await lock(session)
    await member(session, actor)
    row = await session.get(FundOperation, operation_id, populate_existing=True)
    if row is None or row.kind != "loan_offset" or row.employee_id != actor:
        raise FundError("Подтвердить удержание может только заёмщик", 403)
    if row.state == "cancelled":
        raise FundError("Операция отменена")
    if row.consented_at is None:
        row.consented_at = clock.now()
        audit(session, actor, "loan.consent", operation_id=row.id, amount=str(row.amount))
    return row


async def allocations(session: AsyncSession, row: FundOperation) -> list[tuple[str, int, Decimal]]:
    result: list[tuple[str, int, Decimal]] = []
    seen: set[int] = set()
    total = ZERO
    for item in row.details.get("allocations", []):
        oid, amount = int(item["obligation_id"]), Decimal(item["amount"])
        obligation = await session.get(FundObligation, oid)
        if (
            oid in seen
            or obligation is None
            or obligation.employee_id != row.employee_id
            or amount <= 0
        ):
            raise FundError("Проверьте распределение выплаты по обязательствам", 422)
        seen.add(oid)
        result.append(("obligation", oid, -amount))
        total += amount
    if total > row.amount:
        raise FundError("Распределение превышает сумму операции", 422)
    if total < row.amount:
        if row.kind == "payment":
            assert row.employee_id is not None
            result.append(("unallocated", row.employee_id, row.amount - total))
        else:
            raise FundError("Распределите всю сумму зачёта", 422)
    return result


async def confirm_operation(session: AsyncSession, actor: int, operation_id: int) -> FundOperation:
    await lock(session)
    await member(session, actor)
    row = await session.get(FundOperation, operation_id, populate_existing=True)
    if row is None:
        raise FundError("Операция не найдена", 404)
    if row.kind in {"loan_offset", "allocate"}:
        await member(session, actor, leader=True)
    else:
        await basket_owner(session, actor, row.basket_id)
    if row.state == "posted":
        return row
    if row.state != "draft":
        raise FundError("Операция отменена")
    entries: list[tuple[str, int, Decimal]] = []
    kind, amount = row.kind, row.amount
    outgoing = {"expense", "payment", "transfer", "loan_issue"}
    incoming = {
        "contribution",
        "interest",
        "refund",
        "loan_repayment",
        "overpayment_return",
        "compensation_return",
    }
    if kind in outgoing | incoming | {"cash_correction"}:
        assert row.basket_id is not None
        sign = -1 if kind in outgoing else 1
        if kind == "cash_correction":
            sign = int(row.details["correction_direction"])
        entries.append(("cash", row.basket_id, amount * sign))
    if kind == "transfer":
        assert row.target_basket_id is not None
        entries.append(("cash", row.target_basket_id, amount))
    if kind == "compensation_return":
        obligation = await session.get(FundObligation, row.details.get("original_id"))
        if (
            obligation is None
            or obligation.employee_id != row.employee_id
            or obligation.kind != "compensation"
            or amount > -await balance(session, "obligation", obligation.id)
        ):
            raise FundError("Возврат должен относиться к отрицательному остатку компенсации")
        entries.append(("obligation", obligation.id, amount))
    if kind in {"payment", "allocate", "loan_offset"}:
        entries.extend(await allocations(session, row))
    if kind == "allocate":
        assert row.employee_id is not None
        if await balance(session, "unallocated", row.employee_id) < amount:
            raise FundError("Недостаточно нераспределённых выплат")
        entries.append(("unallocated", row.employee_id, -amount))
    if kind in {"loan_issue", "loan_repayment", "loan_offset"}:
        loan = await session.get(FundLoan, row.details.get("loan_id"))
        if loan is None or loan.employee_id != row.employee_id:
            raise FundError("Заём не найден или относится к другому участнику", 422)
        outstanding = await balance(session, "loan", loan.id)
        if kind == "loan_issue":
            if loan.issued or amount != loan.amount or row.occurred_on != loan.issued_on:
                raise FundError("Выдача должна совпадать с одобренными условиями займа")
            others = await session.scalars(
                select(FundLoan).where(
                    FundLoan.employee_id == loan.employee_id,
                    FundLoan.id != loan.id,
                )
            )
            for other in others:
                if await balance(session, "loan", other.id) > 0:
                    raise FundError("Предыдущий заём ещё не погашен")
            loan.issued = True
            entries.append(("loan", loan.id, amount))
        else:
            if not loan.issued or amount > outstanding or row.occurred_on < loan.issued_on:
                raise FundError("Погашение превышает остаток займа или предшествует выдаче")
            if kind == "loan_offset" and row.consented_at is None:
                raise FundError("Нужно согласие участника на конкретную сумму удержания")
            if kind == "loan_offset":
                for account, oid, delta in entries:
                    if account == "obligation" and -delta > await balance(
                        session, "obligation", oid
                    ):
                        raise FundError("Удержание превышает невыплаченное обязательство")
            entries.append(("loan", loan.id, -amount))
    if kind == "overpayment_return":
        assert row.employee_id is not None
        if amount > await balance(session, "overpayment", row.employee_id, row.occurred_on):
            raise FundError("Взнос превышает переплату на дату операции")
        # Заднее число не должно повторно уменьшать уже зачтённую при закрытии переплату.
        closed = await session.scalar(
            select(FundPeriod.month)
            .where(
                FundPeriod.closed_at.is_not(None), FundPeriod.month >= month_start(row.occurred_on)
            )
            .limit(1)
        )
        if closed:
            raise FundError("Взнос за закрытый период требует согласованной корректировки")
        entries.append(("overpayment", row.employee_id, -amount))
    if kind == "refund":
        original = await session.get(FundOperation, row.details.get("original_id"))
        if original is None or original.state != "posted" or original.kind != "expense":
            raise FundError("Укажите проведённый расход, к которому относится возврат")
        reversed_ids = set(
            await session.scalars(
                select(FundOperation.reverses_id).where(
                    FundOperation.state == "posted", FundOperation.reverses_id.is_not(None)
                )
            )
        )
        if original.id in reversed_ids:
            raise FundError("Расход уже отменён обратной операцией")
        refunds = await session.scalars(
            select(FundOperation).where(
                FundOperation.kind == "refund",
                FundOperation.state == "posted",
            )
        )
        returned = sum(
            (
                r.amount
                for r in refunds
                if r.details.get("original_id") == original.id and r.id not in reversed_ids
            ),
            ZERO,
        )
        if returned + amount > original.amount:
            raise FundError("Сумма возвратов превышает исходный расход")
    await post_entries(session, row, actor, entries)
    return row


async def cancel_operation(
    session: AsyncSession, actor: int, operation_id: int, reason: str
) -> FundOperation:
    await lock(session)
    await member(session, actor)
    row = await session.get(FundOperation, operation_id, populate_existing=True)
    if row is None:
        raise FundError("Операция не найдена", 404)
    if row.created_by != actor:
        await basket_owner(session, actor, row.basket_id)
    if row.state == "posted":
        raise FundError("Проведённый факт исправляется связанной обратной операцией")
    row.state = "cancelled"
    audit(session, actor, "operation.cancelled", id=row.id, reason=reason)
    return row


async def reverse_operation(
    session: AsyncSession, actor: int, operation_id: int, reason: str
) -> FundOperation:
    await lock(session)
    row = await session.get(FundOperation, operation_id)
    if (
        row is None
        or row.state != "posted"
        or row.kind in {"opening", "closure", "obligation", "reversal"}
    ):
        raise FundError("Этот факт нельзя исправить обратной денежной операцией")
    if row.basket_id:
        await basket_owner(session, actor, row.basket_id)
    else:
        await member(session, actor, leader=True)
    old = await session.scalar(select(FundOperation).where(FundOperation.reverses_id == row.id))
    if old:
        return old
    if row.kind == "expense":
        reversed_ids = set(
            await session.scalars(
                select(FundOperation.reverses_id).where(
                    FundOperation.state == "posted", FundOperation.reverses_id.is_not(None)
                )
            )
        )
        refunds = await session.scalars(
            select(FundOperation).where(
                FundOperation.kind == "refund", FundOperation.state == "posted"
            )
        )
        if any(
            r.details.get("original_id") == row.id and r.id not in reversed_ids for r in refunds
        ):
            raise FundError("Сначала исправьте возвраты по этому расходу")
    entries = list(
        await session.scalars(select(FundPosting).where(FundPosting.operation_id == row.id))
    )
    for entry in entries:
        if (
            entry.account in {"overpayment", "loan", "unallocated"}
            and await balance(session, entry.account, entry.account_id) - entry.amount < 0
        ):
            raise FundError("После этой операции уже были зависимые зачёты; сначала исправьте их")
    rev = FundOperation(
        request_id=str(uuid4()),
        payload_hash=digest({"reverse": row.id}),
        kind="reversal",
        state="draft",
        amount=row.amount,
        occurred_on=clock.now().astimezone((await load_settings(session)).tz).date(),
        basket_id=row.basket_id,
        target_basket_id=row.target_basket_id,
        employee_id=row.employee_id,
        details={"original_id": row.id},
        reason=reason,
        created_by=actor,
        reverses_id=row.id,
    )
    session.add(rev)
    await session.flush()
    await post_entries(session, rev, actor, [(p.account, p.account_id, -p.amount) for p in entries])
    return rev


async def approve_loan(session: AsyncSession, actor: int, body: LoanInput) -> FundLoan:
    await lock(session)
    await member(session, actor, leader=True)
    await member(session, body.employee_id)
    month = body.issued_on.month + 2
    year = body.issued_on.year + (month - 1) // 12
    month = (month - 1) % 12 + 1
    deadline = date(year, month, min(body.issued_on.day, calendar.monthrange(year, month)[1]))
    if not body.issued_on < body.due_on <= deadline:
        raise FundError("Срок займа должен быть не больше двух календарных месяцев", 422)
    old = await session.scalar(select(FundLoan).where(FundLoan.request_id == str(body.request_id)))
    if old:
        if any(getattr(old, k) != v for k, v in body.model_dump(exclude={"request_id"}).items()):
            raise FundError("Заявка на заём уже сохранена с другими условиями")
        return old
    loans = await session.scalars(select(FundLoan).where(FundLoan.employee_id == body.employee_id))
    for loan in loans:
        if not loan.issued or await balance(session, "loan", loan.id) > 0:
            raise FundError("Есть непогашенный или ещё не выданный одобренный заём")
    row = FundLoan(
        **body.model_dump(exclude={"request_id"}),
        request_id=str(body.request_id),
        approved_by=actor,
    )
    session.add(row)
    await session.flush()
    audit(
        session, actor, "loan.approved", id=row.id, amount=str(row.amount), due_on=str(row.due_on)
    )
    return row


async def reconcile(
    session: AsyncSession, actor: int, body: ReconciliationInput
) -> FundReconciliation:
    await lock(session)
    await basket_owner(session, actor, body.basket_id)
    if body.as_of > clock.now().astimezone((await load_settings(session)).tz).date():
        raise FundError("Нельзя подтвердить будущий остаток", 422)
    old = await session.scalar(
        select(FundReconciliation).where(FundReconciliation.request_id == str(body.request_id))
    )
    if old:
        if old.actual != body.actual or old.as_of != body.as_of or old.basket_id != body.basket_id:
            raise FundError("Этот снимок уже сохранён с другими данными")
        return old
    row = FundReconciliation(
        **body.model_dump(exclude={"request_id"}),
        request_id=str(body.request_id),
        expected=await balance(session, "cash", body.basket_id, body.as_of),
        confirmed_by=actor,
    )
    session.add(row)
    await session.flush()
    audit(
        session,
        actor,
        "basket.reconciled",
        id=row.id,
        actual=str(row.actual),
        expected=str(row.expected),
    )
    return row


async def treasury(session: AsyncSession, actor: int) -> dict[str, Any]:
    await member(session, actor)
    baskets = list(await session.scalars(select(FundBasket).order_by(FundBasket.id)))
    accounts = []
    cash = ZERO
    for basket in baskets:
        amount = await balance(session, "cash", basket.id)
        cash += amount
        recon = await session.scalar(
            select(FundReconciliation)
            .where(
                FundReconciliation.basket_id == basket.id,
            )
            .order_by(FundReconciliation.as_of.desc(), FundReconciliation.id.desc())
            .limit(1)
        )
        difference = None
        if recon:
            difference = recon.actual - await balance(session, "cash", basket.id, recon.as_of)
        accounts.append(
            {
                "id": basket.id,
                "name": basket.name,
                "owner_id": basket.owner_id,
                "balance": str(amount),
                "reconciled_on": str(recon.as_of) if recon else None,
                "actual": str(recon.actual) if recon else None,
                "difference": str(difference) if difference is not None else None,
            }
        )
    obligations = []
    due = ZERO
    for obligation in await session.scalars(
        select(FundObligation).order_by(FundObligation.month, FundObligation.id)
    ):
        remaining = await balance(session, "obligation", obligation.id)
        due += max(ZERO, remaining)
        obligations.append(
            {
                "id": obligation.id,
                "employee_id": obligation.employee_id,
                "month": str(obligation.month),
                "kind": obligation.kind,
                "amount": str(obligation.amount),
                "due": str(remaining),
                "paid": str(await obligation_paid(session, obligation.id)),
                "title": obligation.title,
            }
        )
    closed = list(
        await session.scalars(
            select(FundPeriod.month)
            .where(FundPeriod.closed_at.is_not(None))
            .order_by(FundPeriod.month.desc())
            .limit(3)
        )
    )
    expenses = []
    for month in reversed(closed):
        from teamtime.calc.fund import next_month

        movements = await session.execute(
            select(FundPosting, FundOperation)
            .join(FundOperation)
            .where(
                FundPosting.account == "cash",
                FundOperation.state == "posted",
                FundOperation.occurred_on >= month,
                FundOperation.occurred_on < next_month(month),
            )
        )
        monthly_amount = ZERO
        for posting, operation in movements:
            kind = operation.kind
            if kind == "reversal" and operation.reverses_id:
                original = await session.get(FundOperation, operation.reverses_id)
                kind = original.kind if original else ""
            if kind in {"expense", "payment", "refund"}:
                monthly_amount -= posting.amount
        expenses.append(max(ZERO, monthly_amount))
    free = cash - due
    months = runway(free, expenses)
    return {
        "baskets": accounts,
        "cash": str(cash),
        "obligations": obligations,
        "due": str(due),
        "free": str(free),
        "runway": str(months) if months is not None else None,
        "runway_months_used": len(expenses),
    }
