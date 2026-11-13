"""Явная настройка участников, корзин и начальных остатков без выдуманных нулей."""

from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from teamtime.core import clock
from teamtime.db.fund import FundMember, FundPeriod
from teamtime.db.fund_operations import FundBasket, FundOpening, FundOperation
from teamtime.db.models import Employee, TelegramIdentity
from teamtime.fund_schemas import BasketInput, MemberInput, OpeningInput
from teamtime.services import fund_config
from teamtime.services.fund import FundError, lock, member, valid_month
from teamtime.services.fund_ledger import audit, basket_owner, internal_operation
from teamtime.services.settings import load_settings


async def bootstrap(session: AsyncSession, employee_id: int, joined_on: date) -> FundMember:
    await lock(session)
    if await session.scalar(select(func.count()).select_from(FundMember)):
        raise FundError("Руководитель уже назначен; дальнейшие назначения делает он")
    row = FundMember(
        employee_id=employee_id,
        leader=True,
        active=True,
        joined_on=joined_on,
        appointed_by=f"bootstrap:{employee_id}",
    )
    session.add(row)
    await session.flush()
    audit(session, employee_id, "member.bootstrap", employee_id=employee_id)
    return row


async def set_member(
    session: AsyncSession, actor: int, body: MemberInput, *, demo: bool = False
) -> FundMember:
    await lock(session)
    await member(session, actor, leader=True)
    employee = await session.get(Employee, body.employee_id)
    if employee is None:
        raise FundError("Сотрудник не найден", 404)
    if body.left_on and body.left_on < body.joined_on:
        raise FundError("Дата выхода раньше вступления", 422)
    if not demo:
        linked = await session.scalar(
            select(TelegramIdentity.id)
            .where(
                TelegramIdentity.employee_id == body.employee_id,
                TelegramIdentity.linked_at.is_not(None),
                TelegramIdentity.removed_at.is_(None),
            )
            .limit(1)
        )
        if linked is None:
            raise FundError("Сначала подтвердите привязку Telegram к сотруднику")
    row = await session.get(FundMember, body.employee_id, populate_existing=True)
    if row is None:
        row = FundMember(
            employee_id=body.employee_id, appointed_by=str(actor), joined_on=body.joined_on
        )
        session.add(row)
    elif row.leader and row.active and (not body.leader or not body.active):
        other = await session.scalar(
            select(FundMember.employee_id)
            .where(FundMember.employee_id != row.employee_id, FundMember.leader, FundMember.active)
            .limit(1)
        )
        if other is None:
            raise FundError("Нельзя убрать последнего действующего руководителя")
    if row.joined_on != body.joined_on or row.left_on != body.left_on:
        last_closed = await session.scalar(
            select(func.max(FundPeriod.month)).where(FundPeriod.closed_at.is_not(None))
        )
        if last_closed:
            from teamtime.calc.fund import next_month

            if row.joined_on != body.joined_on or (
                body.left_on and body.left_on < next_month(last_closed)
            ):
                raise FundError("Границы участия затрагивают закрытую историю; нужна корректировка")
    row.active, row.leader, row.joined_on, row.left_on = (
        body.active,
        body.leader,
        body.joined_on,
        body.left_on,
    )
    audit(
        session,
        actor,
        "member.changed",
        employee_id=row.employee_id,
        active=row.active,
        leader=row.leader,
        reason=body.reason,
    )
    await session.flush()
    return row


async def add_basket(session: AsyncSession, actor: int, body: BasketInput) -> FundBasket:
    await lock(session)
    await member(session, actor, leader=True)
    await member(session, body.owner_id)
    if await session.scalar(select(FundBasket.id).where(FundBasket.name == body.name)):
        raise FundError("Корзина с таким названием уже существует")
    if (
        await session.scalar(select(func.count()).select_from(FundBasket).where(FundBasket.active))
        or 0
    ) >= 3:
        raise FundError("В фонде уже настроены три корзины")
    row = FundBasket(name=body.name, owner_id=body.owner_id)
    session.add(row)
    await session.flush()
    audit(session, actor, "basket.created", id=row.id, name=row.name, owner_id=row.owner_id)
    return row


async def basket_opening(
    session: AsyncSession, actor: int, basket_id: int, as_of: date, amount: Decimal, reason: str
) -> None:
    await lock(session)
    await basket_owner(session, actor, basket_id)
    if amount < 0 or as_of > clock.now().astimezone((await load_settings(session)).tz).date():
        raise FundError("Проверьте сумму и дату начального остатка", 422)
    from teamtime.db.fund_operations import FundPosting

    if await session.scalar(
        select(FundOperation.id).where(
            FundOperation.kind == "opening",
            FundOperation.details["basket_id"].as_integer() == basket_id,
        )
    ):
        raise FundError("Начальный остаток уже подтверждён; исправление — отдельная операция")
    if await session.scalar(
        select(FundPosting.id)
        .where(FundPosting.account == "cash", FundPosting.account_id == basket_id)
        .limit(1)
    ):
        raise FundError("В корзине уже есть движения; начальный остаток нужно сверить отдельно")
    await internal_operation(
        session,
        actor,
        key=f"basket-opening:{basket_id}",
        kind="opening",
        day=as_of,
        reason=reason,
        details={"basket_id": basket_id, "as_of": str(as_of)},
        entries=[("cash", basket_id, amount)],
    )


async def overpayment_opening(
    session: AsyncSession, actor: int, employee_id: int, body: OpeningInput
) -> FundOpening:
    await lock(session)
    await member(session, actor, leader=True)
    await member(session, employee_id)
    valid_month(body.month)
    old = await session.get(FundOpening, employee_id)
    if old:
        raise FundError("Начальная переплата уже подтверждена; повторный ввод запрещён")
    if await session.scalar(
        select(FundPeriod.month)
        .where(FundPeriod.closed_at.is_not(None), FundPeriod.month >= body.month)
        .limit(1)
    ):
        raise FundError("Начальный остаток затрагивает закрытую историю")
    row = FundOpening(
        employee_id=employee_id,
        month=body.month,
        amount=body.amount,
        reason=body.reason,
        approved_by=actor,
    )
    session.add(row)
    await internal_operation(
        session,
        actor,
        key=f"overpayment-opening:{employee_id}",
        kind="opening",
        day=body.month - timedelta(days=1),
        reason=body.reason,
        details={"employee_id": employee_id, "month": str(body.month)},
        entries=[("overpayment", employee_id, body.amount)],
    )
    return row


async def activate(session: AsyncSession, actor: int, first_month: date) -> fund_config.FundConfig:
    await lock(session)
    await member(session, actor, leader=True)
    valid_month(first_month)
    config = await fund_config.load(session)
    if config.enabled and config.first_month != first_month:
        raise FundError("Дата начала учёта уже закреплена")
    config.enabled, config.first_month = True, first_month
    await fund_config.save(session, config)
    audit(session, actor, "fund.activated", first_month=str(first_month))
    return config
