"""Вымышленный фонд для демонстрации новых экранов. Рабочие данные не дополняются."""

from datetime import date, timedelta
from decimal import Decimal
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from teamtime.calc.fund_time import Calendar
from teamtime.core import clock
from teamtime.db.fund import FundMember, FundReceipt, FundSourceState
from teamtime.db.fund_operations import FundClaim, FundLoan, FundObligation, FundOperation
from teamtime.db.models import Employee, RawMessage, Source
from teamtime.fund_schemas import BasketInput, OpeningInput
from teamtime.parsing.types import PlanDayKind
from teamtime.services import fund, fund_config, manual
from teamtime.services.fund_ledger import internal_operation
from teamtime.services.fund_setup import add_basket, overpayment_opening

MONTH = date(2026, 11, 1)


async def seed_fund_examples(session: AsyncSession) -> bool:
    """Только уже созданная демо-команда, только первый запуск, без перезаписи правок."""
    if not fund_config.FUND_AVAILABLE:
        return False
    if await session.scalar(select(FundMember.employee_id).limit(1)):
        return False
    if not await session.scalar(
        select(RawMessage.id).where(RawMessage.source == Source.DEMO).limit(1)
    ):
        return False
    people = list(
        await session.scalars(select(Employee).where(Employee.is_active).order_by(Employee.id))
    )
    if len(people) < 3:
        return False
    await fund_config.save(session, fund_config.FundConfig(module_enabled=False))
    lead = people[0].id
    for person in people:
        session.add(
            FundMember(
                employee_id=person.id,
                active=True,
                leader=person.id == lead,
                joined_on=MONTH,
                appointed_by="demo",
            )
        )
    await session.flush()
    days = {
        MONTH + timedelta(days=i): (8 * 3600 if (MONTH + timedelta(days=i)).weekday() < 5 else 0)
        for i in range(30)
    }
    days[date(2026, 11, 4)], days[date(2026, 11, 3)] = 0, 7 * 3600
    await fund.put_calendar(
        session,
        lead,
        Calendar(
            MONTH, "demo-v1", "Учебный календарь демо-команды", days, frozenset({date(2026, 11, 4)})
        ),
        "Пример календаря",
    )
    for index, person in enumerate(people):
        share = Decimal("0.5") if index % 3 == 1 else Decimal(1)
        target = Decimal(45000 + index * 5000) if share < 1 else Decimal(85000 + index * 7000)
        sources = [] if index == 2 else ["Основное место работы", "Учебный проект"]
        await fund.put_terms(
            session,
            lead,
            person.id,
            effective_from=MONTH,
            target=target,
            share=share,
            sources=sources,
            no_other_income=not sources,
            reason="Демонстрационные условия",
        )
        await overpayment_opening(
            session,
            lead,
            person.id,
            OpeningInput(
                month=MONTH,
                amount=Decimal("12500.50")
                if index == 1
                else Decimal("8000")
                if index == 4
                else Decimal(0),
                reason="Учебный начальный остаток",
            ),
        )
        for day in days:
            if day.weekday() >= 5 or not days[day]:
                continue
            start, finish = 10 * 3600, 18 * 3600 if share == 1 else 14 * 3600
            await manual.set_plan_day(
                session,
                employee_id=person.id,
                day=day,
                kind=PlanDayKind.WORK,
                intervals=[(start, finish)],
                actor="demo",
                reason="План демо-фонда",
            )
            if day <= date(2026, 11, 5):
                await manual.set_daily(
                    session,
                    employee_id=person.id,
                    work_date=day,
                    intervals=[(start + (index % 3) * 300, finish)],
                    efficiency=85 + index % 4 * 5,
                    tasks=["Демонстрационная работа"],
                    actor="demo",
                    reason="Факт демо-фонда",
                )
        if sources:
            amount = Decimal(18000 + index * 1300)
            session.add(
                FundReceipt(
                    request_id=str(uuid5(NAMESPACE_URL, f"demo-fund-receipt:{person.id}")),
                    payload_hash="demo",
                    employee_id=person.id,
                    source=sources[0],
                    origin_month=MONTH,
                    applied_month=MONTH,
                    received_on=date(2026, 11, 3),
                    amount=amount,
                    created_by=person.id,
                )
            )
            session.add(
                FundSourceState(
                    employee_id=person.id,
                    month=MONTH,
                    source=sources[0],
                    version=1,
                    complete=index % 2 == 0,
                    confirmed_total=amount,
                    changed_by=person.id,
                    updated_at=clock.now(),
                )
            )
            if index % 2 == 0:
                session.add(
                    FundSourceState(
                        employee_id=person.id,
                        month=MONTH,
                        source=sources[1],
                        version=1,
                        complete=True,
                        confirmed_total=Decimal(0),
                        changed_by=person.id,
                        updated_at=clock.now(),
                    )
                )
    for index, (name, opening_amount, owner) in enumerate(
        (
            ("Счёт фонда · основной", "280000", lead),
            ("Счёт фонда · резервный", "175000", people[1].id),
            ("Наличные", "45000", lead),
        )
    ):
        basket = await add_basket(session, lead, BasketInput(name=name, owner_id=owner))
        await internal_operation(
            session,
            owner,
            key=f"demo-basket:{index}",
            kind="opening",
            day=date(2026, 10, 31),
            reason="Демонстрационный остаток",
            details={"basket_id": basket.id},
            entries=[("cash", basket.id, Decimal(opening_amount))],
        )
    claim = FundClaim(
        request_id=str(uuid5(NAMESPACE_URL, "demo-claim-approved")),
        employee_id=people[2].id,
        month=MONTH,
        spent_on=date(2026, 11, 2),
        amount=Decimal("2340.50"),
        title="Комплект для испытательного стенда",
        state="approved",
        decided_by=lead,
        decided_at=clock.now(),
        decision_reason="Расход согласован",
    )
    session.add(claim)
    session.add(
        FundClaim(
            request_id=str(uuid5(NAMESPACE_URL, "demo-claim-pending")),
            employee_id=people[3].id,
            month=MONTH,
            spent_on=date(2026, 11, 3),
            amount=Decimal("1690"),
            title="Подписка для проекта",
        )
    )
    await session.flush()
    obligation = FundObligation(
        employee_id=claim.employee_id,
        month=MONTH,
        kind="compensation",
        amount=claim.amount,
        origin=f"claim:{claim.id}",
        title=claim.title,
    )
    session.add(obligation)
    await session.flush()
    await internal_operation(
        session,
        lead,
        key=f"claim:{claim.id}",
        kind="obligation",
        day=MONTH,
        reason="Учебная компенсация",
        details={"claim_id": claim.id},
        entries=[("obligation", obligation.id, claim.amount)],
    )
    loan = FundLoan(
        request_id=str(uuid5(NAMESPACE_URL, "demo-fund-loan")),
        employee_id=people[4].id,
        amount=Decimal("15000"),
        issued_on=date(2026, 11, 2),
        due_on=date(2026, 12, 2),
        reason="Беспроцентный заём",
        approved_by=lead,
        issued=True,
    )
    session.add(loan)
    await session.flush()
    from teamtime.db.fund_operations import FundBasket

    basket_id = await session.scalar(select(FundBasket.id).order_by(FundBasket.id).limit(1))
    assert basket_id is not None
    op: FundOperation = await internal_operation(
        session,
        lead,
        key="demo-loan-issued",
        kind="loan_issue",
        day=loan.issued_on,
        reason="Учебная выдача займа",
        details={"loan_id": loan.id},
        entries=[("cash", basket_id, -loan.amount), ("loan", loan.id, loan.amount)],
    )
    op.basket_id, op.employee_id, op.amount = basket_id, loan.employee_id, loan.amount
    await session.flush()
    return True
