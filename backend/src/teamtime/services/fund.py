"""Сбор подтверждённых входных данных фонда. Запись в закрытую историю запрещена."""

from __future__ import annotations

import hashlib
import json
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from teamtime.calc.fund import START, money, month_start, next_month
from teamtime.calc.fund_time import Calendar
from teamtime.core import clock
from teamtime.db.fund import (
    FundAudit,
    FundCalendar,
    FundMember,
    FundPeriod,
    FundReceipt,
    FundSourceState,
    FundTerms,
)
from teamtime.db.models import Employee, TelegramIdentity
from teamtime.services.settings import load_settings


class FundError(ValueError):
    def __init__(self, message: str, status: int = 409) -> None:
        super().__init__(message)
        self.status = status


async def member(session: AsyncSession, employee_id: int, *, leader: bool = False) -> FundMember:
    """Права проверяются при каждом действии; технический пароль не даёт финансовых прав."""
    row = await session.get(FundMember, employee_id, populate_existing=True)
    employee = await session.get(Employee, employee_id, populate_existing=True)
    if row is None or not row.active or employee is None or not employee.is_active:
        raise FundError("Нужна действующая учётная запись участника фонда", 403)
    if leader and not row.leader:
        raise FundError("Действие доступно только руководителю", 403)
    return row


async def telegram_member(session: AsyncSession, telegram_id: int) -> FundMember:
    from teamtime.services.fund_config import require_module

    await require_module(session)
    identity = await session.scalar(
        select(TelegramIdentity).where(TelegramIdentity.telegram_user_id == telegram_id)
    )
    if (
        not identity
        or identity.employee_id is None
        or identity.linked_at is None
        or identity.removed_at is not None
    ):
        raise FundError("Нужна подтверждённая привязка Telegram", 403)
    return await member(session, identity.employee_id)


async def lock(session: AsyncSession) -> None:
    """Все финансовые изменения берут один короткий транзакционный замок.

    Так позднее поступление, подтверждение полноты и будущее закрытие не обгонят друг друга.
    Замок не удерживается во время обращения в Telegram или другие внешние сервисы.
    """
    await session.execute(text("SELECT pg_advisory_xact_lock(685440128035)"))


def valid_month(month: date) -> None:
    if month.day != 1 or month < START or month.year > 2100:
        raise FundError(
            "Новая модель фонда действует с ноября 2026; укажите первый день месяца", 422
        )


async def period(session: AsyncSession, month: date) -> FundPeriod:
    existing = await session.get(FundPeriod, month, populate_existing=True)
    if existing and existing.closed_at:
        return existing
    valid_month(month)
    await session.execute(insert(FundPeriod).values(month=month).on_conflict_do_nothing())
    row = await session.get(FundPeriod, month, populate_existing=True)
    assert row is not None
    return row


async def own(session: AsyncSession, actor: int, employee: int) -> None:
    await member(session, actor)
    await member(session, employee)
    if actor != employee:
        raise FundError("Поступления и их полноту подтверждает сам получатель", 403)


async def put_calendar(
    session: AsyncSession,
    actor: int,
    calendar: Calendar,
    reason: str,
) -> FundCalendar:
    await lock(session)
    await member(session, actor, leader=True)
    valid_month(calendar.month)
    calendar.validate()
    if not reason.strip():
        raise FundError("Укажите основание версии календаря", 422)
    if (await period(session, calendar.month)).closed_at:
        raise FundError("Календарь закрытого месяца изменяется только через корректировку")
    version = (
        await session.scalar(
            select(func.max(FundCalendar.version)).where(FundCalendar.month == calendar.month)
        )
        or 0
    )
    row = FundCalendar(
        month=calendar.month,
        version=version + 1,
        source=calendar.source,
        source_version=calendar.version,
        days={d.isoformat(): n for d, n in calendar.days.items()},
        holidays=sorted(d.isoformat() for d in calendar.holidays),
        created_by=actor,
        reason=reason.strip(),
    )
    session.add(row)
    await session.flush()
    session.add(
        FundAudit(
            actor_id=actor,
            action="calendar.created",
            data={"id": row.id, "version": row.version, "reason": row.reason},
        )
    )
    return row


async def put_terms(
    session: AsyncSession,
    actor: int,
    employee: int,
    *,
    effective_from: date,
    target: Decimal,
    share: Decimal,
    sources: list[str],
    no_other_income: bool,
    reason: str,
) -> FundTerms:
    await lock(session)
    await member(session, actor, leader=True)
    await member(session, employee)
    valid_month(month_start(effective_from))
    if (
        not target.is_finite()
        or not share.is_finite()
        or not 0 <= target <= Decimal("999999999999.99")
        or not 0 < share <= Decimal("9999.9999")
        or target != money(target)
        or share != share.quantize(Decimal("0.0001"))
    ):
        raise FundError("Проверьте целевую сумму и долю ставки", 422)
    sources = [s.strip() for s in sources]
    if (
        not reason.strip()
        or any(not s or len(s) > 100 for s in sources)
        or len(set(sources)) != len(sources)
    ):
        raise FundError("Нужны основание и неповторяющиеся названия источников", 422)
    closed = await session.scalar(
        select(FundPeriod.month)
        .where(FundPeriod.month >= month_start(effective_from), FundPeriod.closed_at.is_not(None))
        .limit(1)
    )
    if closed:
        raise FundError("Изменение затрагивает закрытый месяц; нужна отдельная корректировка")
    revision = (
        await session.scalar(
            select(func.max(FundTerms.revision)).where(
                FundTerms.employee_id == employee,
                FundTerms.effective_from == effective_from,
            )
        )
        or 0
    )
    row = FundTerms(
        employee_id=employee,
        effective_from=effective_from,
        revision=revision + 1,
        target=target,
        share=share,
        sources=sources,
        no_other_income=no_other_income,
        created_by=actor,
        reason=reason.strip(),
    )
    session.add(row)
    await session.flush()
    session.add(
        FundAudit(
            actor_id=actor,
            action="terms.created",
            data={"id": row.id, "employee_id": employee, "reason": row.reason},
        )
    )
    return row


async def add_receipt(
    session: AsyncSession,
    actor: int,
    employee: int,
    *,
    request_id: UUID,
    source: str,
    origin_month: date,
    received_on: date,
    amount: Decimal,
) -> FundReceipt:
    """Повтор запроса возвращает ту же запись, даже если месяц после этого закрыли."""
    await lock(session)
    await own(session, actor, employee)
    if origin_month < START:
        archived = await session.get(FundPeriod, origin_month)
        if not archived or not archived.closed_at:
            raise FundError("Исторический месяц ещё не импортирован и не подтверждён")
    else:
        valid_month(origin_month)
    source = source.strip()
    if (
        not amount.is_finite()
        or not 0 < amount <= Decimal("999999999999.99")
        or amount != money(amount)
        or not source
        or len(source) > 100
    ):
        raise FundError("Нужны источник и положительная сумма фактического поступления", 422)
    timezone = (await load_settings(session)).tz
    if received_on > clock.now().astimezone(timezone).date():
        raise FundError("Будущее поступление нельзя записать как полученное", 422)
    payload = {
        "employee_id": employee,
        "source": source,
        "origin_month": str(origin_month),
        "received_on": str(received_on),
        "amount": str(money(amount)),
        "actor": actor,
    }
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    existing = await session.scalar(
        select(FundReceipt).where(FundReceipt.request_id == str(request_id))
    )
    if existing:
        if existing.payload_hash != digest:
            raise FundError("Этот запрос уже сохранён с другими данными")
        return existing
    applied = origin_month
    # Закрытую историю не переписываем. Перенос один раз, без записи этой же суммы в переплату.
    stored = await session.get(FundPeriod, applied)
    while stored and stored.closed_at:
        applied = max(START, next_month(applied))
        stored = await session.get(FundPeriod, applied)
    await period(session, applied)
    row = FundReceipt(
        request_id=str(request_id),
        payload_hash=digest,
        employee_id=employee,
        source=source,
        origin_month=origin_month,
        applied_month=applied,
        received_on=received_on,
        amount=amount,
        created_by=actor,
    )
    session.add(row)
    state = await session.get(FundSourceState, (employee, applied, source), populate_existing=True)
    if state:
        state.complete = False
        state.version += 1
        state.updated_at = clock.now()
        state.changed_by = actor
    await session.flush()
    session.add(
        FundAudit(
            actor_id=actor,
            action="receipt.created",
            data={
                "id": row.id,
                "employee_id": employee,
                "origin_month": str(origin_month),
                "applied_month": str(applied),
                "amount": str(amount),
            },
        )
    )
    return row


async def confirm_source(
    session: AsyncSession,
    actor: int,
    employee: int,
    *,
    month: date,
    source: str,
    complete: bool,
    expected_total: Decimal,
    expected_version: int,
) -> FundSourceState:
    """Итог проверяется против записей: сообщение «всего» не превращается в ещё одну выплату."""
    await lock(session)
    await own(session, actor, employee)
    source = source.strip()
    if not source or len(source) > 100:
        raise FundError("Укажите источник", 422)
    if not expected_total.is_finite() or expected_total != money(expected_total):
        raise FundError("Неверная ожидаемая сумма", 422)
    if (await period(session, month)).closed_at:
        raise FundError("Полнота данных закрытого месяца сохранена в снимке")
    total = await source_total(session, employee, month, source)
    if total != expected_total:
        raise FundError("Сумма поступлений изменилась; сначала проверьте записи")
    state = await session.get(FundSourceState, (employee, month, source), populate_existing=True)
    if (state.version if state else 0) != expected_version:
        raise FundError("Подтверждение уже изменено; обновите данные")
    if state is None:
        state = FundSourceState(employee_id=employee, month=month, source=source, version=0)
        session.add(state)
    state.version += 1
    state.complete = complete
    state.confirmed_total = expected_total
    state.updated_at = clock.now()
    state.changed_by = actor
    session.add(
        FundAudit(
            actor_id=actor,
            action="source.confirmed",
            data={
                "employee_id": employee,
                "month": str(month),
                "source": source,
                "complete": complete,
                "total": str(expected_total),
                "version": state.version,
            },
        )
    )
    await session.flush()
    return state


async def source_total(session: AsyncSession, employee: int, month: date, source: str) -> Decimal:
    """Полнота подтверждается по сумме с уже утверждёнными исправлениями источника."""
    from teamtime.db.fund_operations import FundAdjustment

    total = await session.scalar(
        select(func.coalesce(func.sum(FundReceipt.amount), 0)).where(
            FundReceipt.employee_id == employee,
            FundReceipt.applied_month == month,
            FundReceipt.source == source,
        )
    )
    correction = await session.scalar(
        select(func.coalesce(func.sum(FundAdjustment.amount), 0)).where(
            FundAdjustment.employee_id == employee,
            FundAdjustment.applied_month == month,
            FundAdjustment.kind == "source",
            FundAdjustment.state == "approved",
            FundAdjustment.after["source"].as_string() == source,
        )
    )
    return Decimal(total or 0) + Decimal(correction or 0)
