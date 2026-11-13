"""Сквозные операции фонда: реальные транзакции PostgreSQL, вымышленные участники."""

import asyncio
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from teamtime.core import clock
from teamtime.db.fund import FundMember, FundPeriod
from teamtime.db.fund_operations import FundObligation
from teamtime.fund_schemas import (
    BasketInput,
    ClaimInput,
    DecisionInput,
    LoanInput,
    OpeningInput,
    OperationInput,
    ReconciliationInput,
)
from teamtime.services import (
    fund,
    fund_config,
    fund_report,
    fund_requests,
    fund_setup,
    team_auth,
)
from teamtime.services import (
    fund_ledger as ledger,
)
from tests import factories as f
from tests.calc.test_fund import calendar

pytestmark = pytest.mark.db
D = Decimal
MONTH = date(2026, 11, 1)


@pytest.fixture
async def team(maker, monkeypatch):
    monkeypatch.setattr(fund_config, "FUND_AVAILABLE", True)
    clock.freeze(datetime(2026, 12, 5, 7, tzinfo=UTC))
    async with maker() as session:
        await fund_config.save(session, fund_config.FundConfig(module_enabled=True))
        lead = await f.employee(session, "Лесов Л.Л.", tg_id=901)
        owner = await f.employee(session, "Речной Р.Р.", tg_id=902)
        normal = await f.employee(session, "Озерова О.О.", tg_id=903)
        for e in (lead, owner, normal):
            session.add(
                FundMember(
                    employee_id=e.id,
                    leader=e.id == lead.id,
                    active=True,
                    joined_on=MONTH,
                    appointed_by="fixture",
                )
            )
        await session.flush()
        a = await fund_setup.add_basket(
            session, lead.id, BasketInput(name="Счёт А", owner_id=lead.id)
        )
        b = await fund_setup.add_basket(
            session, lead.id, BasketInput(name="Счёт Б", owner_id=owner.id)
        )
        await fund_setup.basket_opening(
            session, lead.id, a.id, date(2026, 10, 31), D("100000"), "Проверенный остаток"
        )
        await fund_setup.basket_opening(
            session, owner.id, b.id, date(2026, 10, 31), D("50000"), "Проверенный остаток"
        )
        await session.commit()
        return lead.id, owner.id, normal.id, a.id, b.id


def operation(kind, basket, **changes):
    return OperationInput(
        request_id=uuid4(),
        kind=kind,
        basket_id=basket,
        occurred_on=date(2026, 12, 4),
        amount=D("10000"),
        reason="Проверочный факт",
        **changes,
    )


async def test_draft_does_not_change_money_and_transfer_preserves_total(session, team):
    lead, _, _, a, b = team
    draft = await ledger.new_operation(session, lead, operation("transfer", a, target_basket_id=b))
    assert await ledger.balance(session, "cash", a) == D("100000")
    await ledger.confirm_operation(session, lead, draft.id)
    await ledger.confirm_operation(session, lead, draft.id)
    assert await ledger.balance(session, "cash", a) == D("90000")
    assert await ledger.balance(session, "cash", b) == D("60000")
    assert (await ledger.treasury(session, lead))["cash"] == "150000.00"


async def test_owner_permissions_and_reconciliation_never_add_cash(session, team):
    lead, owner, _, _a, b = team
    with pytest.raises(fund.FundError, match="ответственный"):
        await ledger.new_operation(session, lead, operation("expense", b))
    row = await ledger.reconcile(
        session,
        owner,
        ReconciliationInput(
            request_id=uuid4(),
            basket_id=b,
            as_of=date(2026, 12, 4),
            actual=D("49000"),
            reason="Сверили выписку",
        ),
    )
    assert row.expected == D("50000")
    assert await ledger.balance(session, "cash", b) == D("50000")
    assert (await ledger.treasury(session, lead))["baskets"][1]["difference"] == "-1000.00"


async def test_claim_approval_creates_obligation_not_cash_and_payment_reduces_it(session, team):
    lead, _, employee, a, _ = team
    claim = await fund_requests.new_claim(
        session,
        employee,
        ClaimInput(
            request_id=uuid4(),
            month=MONTH,
            spent_on=date(2026, 11, 20),
            amount=D("1234.56"),
            title="Комплект для стенда",
        ),
    )
    decision = DecisionInput(approve=True, reason="Расход согласован")
    await fund_requests.decide_claim(session, lead, claim.id, decision)
    await fund_requests.decide_claim(session, lead, claim.id, decision)
    obligation = await session.scalar(select(FundObligation))
    assert await ledger.balance(session, "cash", a) == D("100000")
    assert await ledger.balance(session, "obligation", obligation.id) == D("1234.56")
    payment = await ledger.new_operation(
        session,
        lead,
        OperationInput(
            request_id=uuid4(),
            kind="payment",
            basket_id=a,
            employee_id=employee,
            occurred_on=date(2026, 12, 4),
            amount=D("1000"),
            reason="Частичный перевод",
            allocations=[{"obligation_id": obligation.id, "amount": "1000"}],
        ),
    )
    await ledger.confirm_operation(session, lead, payment.id)
    assert await ledger.balance(session, "cash", a) == D("99000")
    assert await ledger.balance(session, "obligation", obligation.id) == D("234.56")


async def test_loans_separate_from_salary_overpayment_and_only_one_outstanding(session, team):
    lead, _, employee, a, _ = team
    body = LoanInput(
        request_id=uuid4(),
        employee_id=employee,
        amount=D("20000"),
        issued_on=date(2026, 12, 4),
        due_on=date(2027, 2, 4),
        reason="Согласован заём",
    )
    loan = await ledger.approve_loan(session, lead, body)
    issue = await ledger.new_operation(
        session,
        lead,
        OperationInput(
            request_id=uuid4(),
            kind="loan_issue",
            basket_id=a,
            employee_id=employee,
            amount=D("20000"),
            occurred_on=body.issued_on,
            loan_id=loan.id,
            reason="Выдача",
        ),
    )
    await ledger.confirm_operation(session, lead, issue.id)
    assert await ledger.balance(session, "cash", a) == D("80000")
    assert await ledger.balance(session, "loan", loan.id) == D("20000")
    assert await ledger.balance(session, "overpayment", employee) == 0
    with pytest.raises(fund.FundError, match="непогашенный"):
        await ledger.approve_loan(session, lead, body.model_copy(update={"request_id": uuid4()}))
    repay = await ledger.new_operation(
        session,
        lead,
        OperationInput(
            request_id=uuid4(),
            kind="loan_repayment",
            basket_id=a,
            employee_id=employee,
            amount=D("5000"),
            occurred_on=body.issued_on,
            loan_id=loan.id,
            reason="Частичный возврат",
        ),
    )
    await ledger.confirm_operation(session, lead, repay.id)
    assert await ledger.balance(session, "loan", loan.id) == D("15000")


async def test_loan_offset_needs_participant_and_does_not_create_fictitious_cash(session, team):
    lead, _, employee, a, _ = team
    loan = await ledger.approve_loan(
        session,
        lead,
        LoanInput(
            request_id=uuid4(),
            employee_id=employee,
            amount=D("10000"),
            issued_on=date(2026, 12, 4),
            due_on=date(2027, 1, 4),
            reason="Заём",
        ),
    )
    issue = await ledger.new_operation(
        session, lead, operation("loan_issue", a, employee_id=employee, loan_id=loan.id)
    )
    await ledger.confirm_operation(session, lead, issue.id)
    obligation = FundObligation(
        employee_id=employee,
        month=MONTH,
        kind="salary",
        amount=D("14000"),
        origin="fixture:salary",
        title="Доплата",
    )
    session.add(obligation)
    await session.flush()
    await ledger.internal_operation(
        session,
        lead,
        key="fixture:obligation",
        kind="obligation",
        day=MONTH,
        reason="Тестовое начисление",
        details={},
        entries=[("obligation", obligation.id, D("14000"))],
    )
    offset = await ledger.new_operation(
        session,
        lead,
        operation(
            "loan_offset",
            None,
            employee_id=employee,
            loan_id=loan.id,
            allocations=[{"obligation_id": obligation.id, "amount": "10000"}],
        ),
    )
    with pytest.raises(fund.FundError, match="согласие"):
        await ledger.confirm_operation(session, lead, offset.id)
    with pytest.raises(fund.FundError):
        await ledger.consent(session, lead, offset.id)
    await ledger.consent(session, employee, offset.id)
    await ledger.confirm_operation(session, lead, offset.id)
    assert await ledger.balance(session, "cash", a) == D("90000")
    assert await ledger.balance(session, "loan", loan.id) == 0
    assert await ledger.balance(session, "obligation", obligation.id) == D("4000")


async def prepare_month(session, lead, people):
    await fund.put_calendar(session, lead, calendar(), "Проверочный календарь")
    for employee in people:
        await fund.put_terms(
            session,
            lead,
            employee,
            effective_from=MONTH,
            target=D("80000"),
            share=D(1),
            sources=["Источник А"],
            no_other_income=False,
            reason="Условия",
        )
        await fund_setup.overpayment_opening(
            session,
            lead,
            employee,
            OpeningInput(month=MONTH, amount=D(0), reason="Подтверждённый ноль"),
        )
        await fund.confirm_source(
            session,
            employee,
            employee,
            month=MONTH,
            source="Источник А",
            complete=True,
            expected_total=D(0),
            expected_version=0,
        )
        # Полное согласованное отсутствие, без фиктивных рабочих часов.
        from teamtime.db.fund_operations import FundTimeRequest

        session.add(
            FundTimeRequest(
                request_id=str(uuid4()),
                employee_id=employee,
                kind="sick",
                days=[f"2026-11-{day:02d}" for day in range(1, 31)],
                state="approved",
                seconds=0,
                reason="Согласованное отсутствие",
                evidence={},
                decided_by=lead,
                decided_at=clock.now(),
            )
        )
    await session.flush()


async def test_closure_snapshot_idempotence_and_no_money_on_accrual(maker, team):
    lead, owner, employee, a, _ = team
    async with maker() as session:
        await prepare_month(session, lead, (lead, owner, employee))
        report = await fund_report.report(session, lead, MONTH)
        assert report["can_close"], report
        fp = report["fingerprint"]
        await session.commit()

    async def close():
        async with maker() as session:
            result = await fund_report.close_month(session, lead, MONTH, fp, "Проверено")
            await session.commit()
            return result

    reports = await asyncio.gather(close(), close())
    assert all(r["closed"] for r in reports)
    async with maker() as session:
        assert await session.scalar(select(func.count()).select_from(FundObligation)) == 3
        assert await ledger.balance(session, "cash", a) == D("100000")
        assert (await ledger.treasury(session, lead))["due"] == "240000.00"
        saved = (await session.get(FundPeriod, MONTH)).snapshot
        assert saved["rows"][0]["amounts"]["salary"] == "80000.00"


async def test_pending_source_or_changed_input_prevents_close(session, team):
    lead, owner, employee, _, _ = team
    await prepare_month(session, lead, (lead, owner, employee))
    report = await fund_report.report(session, lead, MONTH)
    await fund.confirm_source(
        session,
        employee,
        employee,
        month=MONTH,
        source="Источник А",
        complete=False,
        expected_total=D(0),
        expected_version=1,
    )
    with pytest.raises(fund.FundError, match="изменились"):
        await fund_report.close_month(session, lead, MONTH, report["fingerprint"], "Проверено")
    current = await fund_report.report(session, lead, MONTH)
    assert not current["can_close"]


async def test_telegram_login_requires_confirmation_and_secret_is_single_use(session, team):
    request = await team_auth.begin_login(session)
    assert await team_auth.finish_login(session, request["code"], request["secret"]) == (None, None)
    with pytest.raises(fund.FundError):
        await team_auth.finish_login(session, request["code"], "wrong-secret")
    await team_auth.confirm_login(session, request["code"], 903)
    token, person = await team_auth.finish_login(session, request["code"], request["secret"])
    assert person.employee_id == team[2]
    assert (await team_auth.authenticate(session, token)).employee_id == team[2]
    with pytest.raises(fund.FundError):
        await team_auth.finish_login(session, request["code"], request["secret"])
    display = await team_auth.issue_session(session, None, None, display=True)
    assert await team_auth.display_access(session, display)
    with pytest.raises(fund.FundError):
        await team_auth.authenticate(session, display)
