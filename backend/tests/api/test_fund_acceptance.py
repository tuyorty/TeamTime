"""Приёмочные сценарии: границы доступа, общий расчёт, история и корректировки."""

from datetime import date
from decimal import Decimal
from io import BytesIO
from uuid import uuid4

import pytest
from openpyxl import load_workbook
from sqlalchemy import select

from teamtime.db.fund import FundPeriod
from teamtime.db.fund_operations import FundObligation
from teamtime.fund_schemas import ClaimInput, CorrectionInput, DecisionInput, OperationInput
from teamtime.importer import fund as migration
from teamtime.services import fund, fund_config, fund_corrections, fund_report, fund_requests
from teamtime.services import fund_ledger as ledger
from tests.api.conftest import ADMIN_HEADERS
from tests.api.test_fund_workflows import MONTH, prepare_month

pytest_plugins = ["tests.api.test_fund_workflows"]
pytestmark = pytest.mark.db
D = Decimal


async def login(client, employee):
    response = await client.post(
        "/team/demo-login", json={"employee_id": employee}, headers=ADMIN_HEADERS
    )
    assert response.status_code == 200, response.text


async def test_member_sees_other_report_but_cannot_change_it(client, maker, team):
    lead, owner, employee, _, _ = team
    async with maker() as session:
        await prepare_month(session, lead, (lead, owner, employee))
        await fund_config.save(session, fund_config.FundConfig(module_enabled=True, enabled=True))
        await session.commit()
    assert (await client.get("/fund/overview")).status_code == 401
    assert (await client.get("/today")).status_code == 401
    await login(client, employee)
    report = (await client.get(f"/fund/months/{MONTH}")).json()
    assert len(report["rows"]) == 3
    response = await client.post(
        f"/fund/months/{MONTH}/close",
        headers=ADMIN_HEADERS,
        json={"fingerprint": report["fingerprint"], "reason": "Проверка"},
    )
    assert response.status_code == 403
    assert (await client.get("/inbox")).status_code == 403
    await client.post("/auth/login", json={"password": "secret"})
    assert (
        await client.post(
            "/fund/bonuses",
            headers=ADMIN_HEADERS,
            json={
                "request_id": str(uuid4()),
                "employee_id": employee,
                "month": str(MONTH),
                "amount": "1000",
                "reason": "Проверка",
            },
        )
    ).status_code == 403


async def test_same_hours_in_fund_month_and_export_and_display_scope(client, maker, team):
    lead, owner, employee, _, _ = team
    async with maker() as session:
        await prepare_month(session, lead, (lead, owner, employee))
        await fund_config.save(session, fund_config.FundConfig(module_enabled=True, enabled=True))
        await session.commit()
    await login(client, lead)
    assert (await client.get("/export/finances/2026/11.xlsx")).status_code == 409
    report = (await client.get(f"/fund/months/{MONTH}")).json()
    month = (await client.get("/months/2026/11?history=1")).json()
    for row, monthly in zip(
        report["rows"], sorted(month["rows"], key=lambda r: r["employee"]["id"]), strict=True
    ):
        assert monthly["summary"]["fund_model"]
        assert monthly["summary"]["total_sec"] == row["credited_sec"]
        assert monthly["summary"]["norm_sec"] == row["norm_sec"]
        assert D(monthly["summary"]["fund_salary"]) == D(row["amounts"]["salary"])
    response = await client.get(f"/fund/export/{MONTH}.xlsx?employee_id={employee}")
    workbook = load_workbook(BytesIO(response.content))
    sheet = workbook.active
    assert sheet.max_row == 2
    assert D(str(sheet.cell(2, 7).value)) == D("80000")
    token = (await client.post("/team/display-token", headers=ADMIN_HEADERS)).json()["token"]
    await client.post("/team/logout", headers=ADMIN_HEADERS)
    assert (
        await client.post("/team/display-login", headers=ADMIN_HEADERS, json={"token": token})
    ).status_code == 200
    screen = await client.get("/display/today")
    assert screen.status_code == 200
    assert screen.json()["feed"] == []
    assert all(
        "daily" not in r["cell"] and "phone" not in r["employee"] for r in screen.json()["rows"]
    )
    assert (await client.get("/fund/overview")).status_code == 401
    assert (await client.get("/employees")).status_code == 401


async def test_import_dry_run_digest_and_replay_do_not_duplicate_cash(session, team):
    lead, _, employee, a, _ = team
    provenance = migration.Provenance(
        book="Архив", sheet="Октябрь", cells=["A1:C2"], note="Сверено"
    )
    values = dict.fromkeys(migration.AMOUNT_KEYS, "0.00")
    values.update(supplement="1000", accrued="1000", paid="700", due="300")
    package = migration.Package(
        package_id="fictional-archive",
        as_of=date(2026, 11, 4),
        source="Тестовый архив",
        approved_by_leader=True,
        expected_cash="0",
        expected_overpayments="200",
        expected_due="300",
        overpayments=[
            migration.OverpaymentOpening(employee_id=employee, amount="200", source=provenance)
        ],
        history=[
            migration.HistoricalRow(
                month=date(2026, 10, 1),
                employee_id=employee,
                norm_sec=160 * 3600,
                effective_sec=160 * 3600,
                penalty_sec=0,
                credited_sec=160 * 3600,
                amounts=values,
                source=provenance,
            )
        ],
        obligations=[
            migration.HistoricalObligation(
                key="october",
                employee_id=employee,
                month=date(2026, 10, 1),
                kind="salary",
                amount="1000",
                paid="700",
                title="Историческая доплата",
                source=provenance,
            )
        ],
    )
    preview = await migration.inspect(session, lead, package)
    assert preview["ready"], preview
    assert await session.get(FundPeriod, date(2026, 10, 1)) is None
    with pytest.raises(fund.FundError, match="изменилось"):
        await migration.apply(session, lead, package, "wrong")
    await migration.apply(session, lead, package, preview["digest"])
    assert (await migration.apply(session, lead, package, preview["digest"]))["already_applied"]
    assert await ledger.balance(session, "cash", a) == D("100000")
    assert await ledger.balance(session, "overpayment", employee) == D("200")
    report = await fund_report.report(session, lead, date(2026, 10, 1))
    assert report["rows"][0]["amounts"]["due"] == "300.00"
    receipt = await fund.add_receipt(
        session,
        employee,
        employee,
        request_id=uuid4(),
        source="Источник А",
        origin_month=date(2026, 10, 1),
        received_on=date(2026, 12, 4),
        amount=D("5000"),
    )
    assert receipt.applied_month == MONTH
    assert await ledger.balance(session, "overpayment", employee) == D("200")


async def test_compensation_reduction_after_payment_keeps_salary_and_cash_unchanged(session, team):
    lead, owner, employee, basket, _ = team
    await prepare_month(session, lead, (lead, owner, employee))
    claim = await fund_requests.new_claim(
        session,
        employee,
        ClaimInput(
            request_id=uuid4(), month=MONTH, spent_on=MONTH, amount="1000.25", title="Материалы"
        ),
    )
    await fund_requests.decide_claim(
        session, lead, claim.id, DecisionInput(approve=True, reason="Согласовано")
    )
    report = await fund_report.report(session, lead, MONTH)
    await fund_report.close_month(session, lead, MONTH, report["fingerprint"], "Проверено")
    obligation = await session.scalar(
        select(FundObligation).where(
            FundObligation.employee_id == employee, FundObligation.kind == "compensation"
        )
    )
    payment = await ledger.new_operation(
        session,
        lead,
        OperationInput(
            request_id=uuid4(),
            kind="payment",
            occurred_on=date(2026, 12, 4),
            amount="1000.25",
            basket_id=basket,
            employee_id=employee,
            reason="Выплачено",
            allocations=[{"obligation_id": obligation.id, "amount": "1000.25"}],
        ),
    )
    await ledger.confirm_operation(session, lead, payment.id)
    old_cash = await ledger.balance(session, "cash", basket)
    correction = await fund_corrections.propose(
        session,
        employee,
        CorrectionInput(
            request_id=uuid4(),
            employee_id=employee,
            origin_month=MONTH,
            kind="compensation",
            corrected_amount="800.00",
            reason="Уточнена доля расходов",
        ),
    )
    await fund_corrections.decide(
        session, lead, correction.id, DecisionInput(approve=True, reason="Проверено")
    )
    assert await ledger.balance(session, "cash", basket) == old_cash
    assert await ledger.balance(session, "overpayment", employee) == 0
    credit = await session.scalar(
        select(FundObligation).where(FundObligation.origin == f"adjustment:{correction.id}")
    )
    assert await ledger.balance(session, "obligation", credit.id) == D("-200.25")
    assert (
        next(
            r
            for r in (await session.get(FundPeriod, MONTH)).snapshot["rows"]
            if r["employee"]["id"] == employee
        )["amounts"]["compensation"]
        == "1000.25"
    )
    refund = await ledger.new_operation(
        session,
        lead,
        OperationInput(
            request_id=uuid4(),
            kind="compensation_return",
            occurred_on=date(2026, 12, 5),
            amount="200.25",
            employee_id=employee,
            basket_id=basket,
            original_id=credit.id,
            reason="Фактический добровольный возврат",
        ),
    )
    await ledger.confirm_operation(session, lead, refund.id)
    assert await ledger.balance(session, "obligation", credit.id) == 0
    assert await ledger.balance(session, "cash", basket) == old_cash + D("200.25")


async def test_per_interval_efficiency_matches_day_result(session, team):
    from teamtime.services import facts, manual

    daily = await manual.set_daily(
        session,
        employee_id=team[2],
        work_date=MONTH,
        intervals=[(9 * 3600, 13 * 3600), (14 * 3600, 18 * 3600)],
        efficiency=None,
        interval_efficiencies=[50, 100],
        actor="test",
        reason="Разная эффективность",
    )
    assert facts.fact_input(daily).effective_seconds == 6 * 3600
    amended = await manual.set_daily(
        session, employee_id=team[2], work_date=MONTH, tasks=["Уточнённая задача"], actor="test"
    )
    assert facts.fact_input(amended).effective_seconds == 6 * 3600


async def test_closed_time_change_is_reviewed_without_rewriting_money(session, team):
    from teamtime.services import fund_changes, manual

    lead, owner, employee, _, _ = team
    await prepare_month(session, lead, (lead, owner, employee))
    report = await fund_report.report(session, lead, MONTH)
    await fund_report.close_month(session, lead, MONTH, report["fingerprint"], "Сверено")
    before = (await fund_report.report(session, lead, MONTH))["rows"]
    await manual.set_daily(
        session,
        employee_id=employee,
        work_date=MONTH,
        intervals=[(9 * 3600, 17 * 3600)],
        efficiency=100,
        actor="Руководитель",
        reason="Позднее уточнение",
    )
    queue = await fund_changes.pending(session)
    assert len(queue) == 1
    assert queue[0]["employee_id"] == employee
    event = queue[0]["event_id"]
    assert (await fund_report.report(session, lead, MONTH))["rows"] == before
    with pytest.raises(fund.FundError):
        await fund_changes.reviewed(session, employee, event, "Проверено")
    await manual.set_daily(
        session,
        employee_id=employee,
        work_date=MONTH,
        intervals=[(9 * 3600, 18 * 3600)],
        efficiency=100,
        actor="Руководитель",
        reason="Ещё одно уточнение",
    )
    with pytest.raises(fund.FundError, match="изменились снова"):
        await fund_changes.reviewed(session, lead, event, "Устаревшая проверка")
    event = (await fund_changes.pending(session))[0]["event_id"]
    await fund_changes.reviewed(
        session, lead, event, "Проверено, корректировка согласуется отдельно"
    )
    await session.flush()
    assert await fund_changes.pending(session) == []
    assert (await fund_report.report(session, lead, MONTH))["rows"] == before
