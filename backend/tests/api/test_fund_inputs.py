"""Фонд: права, конкурирующие записи и закрытая история на отдельной тестовой БД."""

import asyncio
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from teamtime.core import clock
from teamtime.db.fund import (
    FundAudit,
    FundMember,
    FundPeriod,
    FundReceipt,
    FundSourceState,
    FundTerms,
)
from teamtime.db.models import TelegramIdentity
from teamtime.services import fund, fund_config
from tests import factories as f
from tests.calc.test_fund import calendar

pytestmark = pytest.mark.db
MONTH = date(2026, 11, 1)
D = Decimal


@pytest.fixture
async def participants(maker, monkeypatch):
    monkeypatch.setattr(fund_config, "FUND_AVAILABLE", True)
    clock.freeze(datetime(2026, 12, 5, 7, tzinfo=UTC))
    async with maker() as session:
        await fund_config.save(session, fund_config.FundConfig(module_enabled=True))
        leader = await f.employee(session, "Соколов С.С.", tg_id=701)
        employee = await f.employee(session, "Соколов С.А.", tg_id=702)
        session.add_all(
            [
                FundMember(
                    employee_id=leader.id, leader=True, joined_on=MONTH, appointed_by="fixture"
                ),
                FundMember(
                    employee_id=employee.id, leader=False, joined_on=MONTH, appointed_by="fixture"
                ),
            ]
        )
        await session.commit()
        return leader.id, employee.id


def receipt(employee, **changes):
    return {
        "actor": employee,
        "employee": employee,
        "request_id": uuid4(),
        "source": "Источник А",
        "origin_month": MONTH,
        "received_on": date(2026, 11, 20),
        "amount": D("10000.25"),
        **changes,
    }


def terms(**changes):
    return {
        "effective_from": MONTH,
        "target": D("50000"),
        "share": D("0.5"),
        "sources": ["Источник А"],
        "no_other_income": False,
        "reason": "Согласованы условия",
        **changes,
    }


async def test_only_verified_telegram_binding_and_active_membership(session, participants):
    leader, employee = participants
    assert (await fund.telegram_member(session, 702)).employee_id == employee
    with pytest.raises(fund.FundError):
        await fund.telegram_member(session, 999)
    identity = await session.scalar(
        select(TelegramIdentity).where(TelegramIdentity.telegram_user_id == 702)
    )
    identity.removed_at = clock.now()
    await session.flush()
    with pytest.raises(fund.FundError):
        await fund.telegram_member(session, 702)
    row = await session.get(FundMember, leader)
    row.active = False
    await session.flush()
    with pytest.raises(fund.FundError):
        await fund.member(session, leader)


async def test_only_leader_sets_terms_and_versions_are_append_only(session, participants):
    leader, employee = participants
    with pytest.raises(fund.FundError, match="руководителю"):
        await fund.put_terms(session, employee, employee, **terms())
    first = await fund.put_terms(session, leader, employee, **terms())
    second = await fund.put_terms(session, leader, employee, **terms(target=D("55000")))
    assert first.id != second.id
    assert (first.revision, second.revision) == (1, 2)
    assert first.target == D("50000")
    assert await session.scalar(select(func.count()).select_from(FundTerms)) == 2


async def test_closed_period_prevents_calendar_and_terms_rewrite(session, participants):
    leader, employee = participants
    first = await fund.put_calendar(session, leader, calendar(), "Проверочный календарь")
    second = await fund.put_calendar(session, leader, calendar(), "Вторая версия")
    assert (first.version, second.version) == (1, 2)
    p = await session.get(FundPeriod, MONTH)
    p.closed_at, p.closed_by, p.snapshot = clock.now(), leader, {"fixture": True}
    await session.flush()
    with pytest.raises(fund.FundError, match="закрытого"):
        await fund.put_calendar(session, leader, calendar(), "Заменить")
    with pytest.raises(fund.FundError, match="закрытый"):
        await fund.put_terms(session, leader, employee, **terms())


async def test_parallel_receipt_retries_create_one_entry_and_one_audit(maker, participants):
    _, employee = participants
    payload = receipt(employee)

    async def save():
        async with maker() as session:
            row = await fund.add_receipt(session, **payload)
            await session.commit()
            return row.id

    ids = await asyncio.gather(save(), save(), save())
    assert len(set(ids)) == 1
    async with maker() as session:
        assert await session.scalar(select(func.count()).select_from(FundReceipt)) == 1
        assert await session.scalar(select(func.count()).select_from(FundAudit)) == 1
        with pytest.raises(fund.FundError, match="другими данными"):
            await fund.add_receipt(session, **{**payload, "amount": D("20000.25")})


async def test_leader_cannot_claim_actual_income_on_behalf_of_employee(session, participants):
    leader, employee = participants
    with pytest.raises(fund.FundError, match="сам получатель"):
        await fund.add_receipt(session, **receipt(employee, actor=leader))


async def test_late_receipt_uses_next_open_month_without_editing_snapshot(session, participants):
    leader, employee = participants
    for m in (MONTH, date(2026, 12, 1)):
        p = await fund.period(session, m)
        p.closed_at, p.closed_by, p.snapshot = clock.now(), leader, {"salary": "123.45"}
    await session.flush()
    payload = receipt(employee)
    row = await fund.add_receipt(session, **payload)
    assert row.applied_month == date(2027, 1, 1)
    assert row.origin_month == MONTH
    assert (await session.get(FundPeriod, MONTH)).snapshot == {"salary": "123.45"}
    # Повтор после закрытия месяца применения не переносит запись ещё раз.
    p = await session.get(FundPeriod, row.applied_month)
    p.closed_at, p.closed_by, p.snapshot = clock.now(), leader, {"receipt": row.id}
    await session.flush()
    repeat = await fund.add_receipt(session, **payload)
    assert repeat.id == row.id and repeat.applied_month == date(2027, 1, 1)


async def test_payment_date_after_origin_month_does_not_shift_open_month(session, participants):
    _, employee = participants
    row = await fund.add_receipt(session, **receipt(employee, received_on=date(2026, 12, 2)))
    assert row.applied_month == MONTH


async def test_zero_requires_explicit_confirmation_not_zero_cash_entry(session, participants):
    _, employee = participants
    row = await fund.confirm_source(
        session,
        employee,
        employee,
        month=MONTH,
        source="Источник А",
        complete=True,
        expected_total=D(0),
        expected_version=0,
    )
    assert row.complete and row.confirmed_total == 0
    assert await session.scalar(select(func.count()).select_from(FundReceipt)) == 0
    with pytest.raises(fund.FundError, match="положительная"):
        await fund.add_receipt(session, **receipt(employee, amount=D(0)))


async def test_partial_receipts_and_total_confirmation_cannot_double_income(session, participants):
    _, employee = participants
    await fund.add_receipt(session, **receipt(employee, amount=D("10000")))
    await fund.add_receipt(session, **receipt(employee, amount=D("10000")))
    state = await fund.confirm_source(
        session,
        employee,
        employee,
        month=MONTH,
        source="Источник А",
        complete=True,
        expected_total=D("20000"),
        expected_version=0,
    )
    assert state.complete
    assert await session.scalar(select(func.sum(FundReceipt.amount))) == D("20000")
    with pytest.raises(fund.FundError, match="изменилась"):
        await fund.confirm_source(
            session,
            employee,
            employee,
            month=MONTH,
            source="Источник А",
            complete=True,
            expected_total=D("10000"),
            expected_version=1,
        )
    # Новый факт требует свежего подтверждения, прежняя галочка полноты не остаётся.
    await fund.add_receipt(session, **receipt(employee, amount=D("500")))
    state = await session.get(FundSourceState, (employee, MONTH, "Источник А"))
    assert not state.complete and state.version == 2
    with pytest.raises(fund.FundError, match="уже изменено"):
        await fund.confirm_source(
            session,
            employee,
            employee,
            month=MONTH,
            source="Источник А",
            complete=True,
            expected_total=D("20500"),
            expected_version=1,
        )


async def test_receipt_day_uses_team_timezone(session, participants):
    _, employee = participants
    clock.freeze(datetime(2026, 11, 20, 20, tzinfo=UTC))
    await fund.add_receipt(session, **receipt(employee, received_on=date(2026, 11, 21)))
    with pytest.raises(fund.FundError, match="Будущее"):
        await fund.add_receipt(session, **receipt(employee, received_on=date(2026, 11, 22)))


async def test_historical_rules_are_not_implicitly_migrated(session, participants):
    leader, employee = participants
    with pytest.raises(fund.FundError, match="с ноября"):
        await fund.put_terms(session, leader, employee, **terms(effective_from=date(2026, 10, 1)))
