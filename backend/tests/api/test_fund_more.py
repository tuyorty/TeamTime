"""Исправления, исходники и защита от двойного учёта в финансовых сценариях."""

from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy import func, select

from teamtime.bot.fund_notifications import send_fund_notifications
from teamtime.core import clock
from teamtime.db.fund import FundReceipt
from teamtime.db.fund_operations import FundNotification
from teamtime.db.models import TelegramIdentity
from teamtime.fund_schemas import CorrectionInput, DecisionInput, LoanInput, ReceiptInput
from teamtime.services import fund, fund_bot, fund_config, fund_corrections, fund_ledger
from tests.api.test_fund_workflows import MONTH, operation

pytest_plugins = ["tests.api.test_fund_workflows"]

pytestmark = pytest.mark.db
D = Decimal


async def test_source_correction_changes_completion_total_once(session, team):
    lead, _, employee, _, _ = team
    receipt = await fund.add_receipt(
        session,
        employee,
        employee,
        **ReceiptInput(
            request_id=uuid4(),
            source="Источник",
            origin_month=MONTH,
            received_on=date(2026, 11, 20),
            amount=D("1500"),
        ).model_dump(),
    )
    change = await fund_corrections.propose(
        session,
        employee,
        CorrectionInput(
            request_id=uuid4(),
            employee_id=employee,
            kind="source",
            origin_month=MONTH,
            reference_id=receipt.id,
            corrected_amount=D("1000"),
            reason="В исходном сообщении опечатка",
        ),
    )
    decision = DecisionInput(approve=True, reason="Проверено по исходной выплате")
    await fund_corrections.decide(session, lead, change.id, decision)
    await fund_corrections.decide(session, lead, change.id, decision)
    assert await fund.source_total(session, employee, MONTH, "Источник") == D("1000")
    state = await fund.confirm_source(
        session,
        employee,
        employee,
        month=MONTH,
        source="Источник",
        complete=True,
        expected_total=D("1000"),
        expected_version=0,
    )
    assert state.confirmed_total == D("1000")
    assert receipt.amount == D("1500")


async def test_cash_snapshot_does_not_recount_old_operation(session, team):
    lead, _, _, basket, _ = team
    body = operation("contribution", basket).model_copy(update={"occurred_on": date(2026, 10, 31)})
    row = await fund_ledger.new_operation(session, lead, body)
    with pytest.raises(fund.FundError, match="начальный остаток"):
        await fund_ledger.confirm_operation(session, lead, row.id)
    assert await fund_ledger.balance(session, "cash", basket) == D("100000")


async def test_reversed_refund_does_not_prevent_correct_refund(session, team):
    lead, _, _, basket, _ = team
    expense = await fund_ledger.new_operation(session, lead, operation("expense", basket))
    await fund_ledger.confirm_operation(session, lead, expense.id)
    refund = await fund_ledger.new_operation(
        session, lead, operation("refund", basket, original_id=expense.id)
    )
    await fund_ledger.confirm_operation(session, lead, refund.id)
    with pytest.raises(fund.FundError, match="Сначала исправьте возвраты"):
        await fund_ledger.reverse_operation(session, lead, expense.id, "Ошибка")
    await fund_ledger.reverse_operation(session, lead, refund.id, "Возврат записан ошибочно")
    replacement = await fund_ledger.new_operation(
        session, lead, operation("refund", basket, original_id=expense.id)
    )
    await fund_ledger.confirm_operation(session, lead, replacement.id)
    assert await fund_ledger.balance(session, "cash", basket) == D("100000")


async def link(session, employee, tg_id):
    identity = await session.scalar(
        select(TelegramIdentity).where(TelegramIdentity.telegram_user_id == tg_id)
    )
    if identity is None:
        identity = TelegramIdentity(
            telegram_user_id=tg_id, employee_id=employee, display_name="Участник"
        )
        session.add(identity)
    identity.linked_at, identity.dm_chat_id = clock.now(), tg_id
    await session.flush()


async def test_bot_replayed_input_and_confirmation_are_idempotent(session, team):
    _, _, employee, _, _ = team
    await link(session, employee, 903)
    row = await fund_bot.create_draft(session, 903, "receipt", MONTH)
    await fund_bot.answer(session, 903, row.id, "Источник", "message:1")
    await fund_bot.answer(session, 903, row.id, "Источник", "message:1")
    assert row.payload["step"] == 1
    await fund_bot.answer(session, 903, row.id, "1 234,56", "message:2")
    await fund_bot.answer(session, 903, row.id, "2026-11-20", "message:3")
    assert await session.scalar(select(func.count()).select_from(FundReceipt)) == 0
    await fund_bot.submit(session, 903, row.id)
    await fund_bot.submit(session, 903, row.id)
    assert await session.scalar(select(func.count()).select_from(FundReceipt)) == 1
    receipt = await session.scalar(select(FundReceipt))
    assert receipt.amount == D("1234.56")


async def test_bot_cannot_submit_someone_elses_draft(session, team):
    lead, _, employee, _, _ = team
    await link(session, lead, 901)
    await link(session, employee, 903)
    row = await fund_bot.create_draft(session, 903, "claim", MONTH)
    with pytest.raises(fund.FundError, match="другому"):
        await fund_bot.submit(session, 901, row.id)


async def test_notification_timeout_is_not_retried_after_restart(session, maker, team):
    lead, owner, _, _, _ = team
    await link(session, lead, 901)
    await link(session, owner, 902)
    config = await fund_config.load(session)
    config.enabled = True
    await fund_config.save(session, config)
    await session.commit()
    clock.freeze(datetime(2026, 11, 18, 7, 1, tzinfo=UTC))
    bot = AsyncMock()
    bot.send_message.side_effect = TimeoutError
    assert await send_fund_notifications(bot, maker) == 0
    attempts = bot.send_message.call_count
    assert attempts >= 2
    await send_fund_notifications(bot, maker)
    assert bot.send_message.call_count == attempts
    assert await session.scalar(select(func.count()).select_from(FundNotification)) == attempts
    clock.freeze(datetime(2026, 11, 19, 12, tzinfo=UTC))
    await send_fund_notifications(bot, maker)
    assert bot.send_message.call_count == attempts


async def test_overdue_loan_warns_once_outside_source_request_dates(session, maker, team):
    lead, _, employee, basket, _ = team
    await link(session, lead, 901)
    config = await fund_config.load(session)
    config.enabled = True
    await fund_config.save(session, config)
    loan = await fund_ledger.approve_loan(
        session,
        lead,
        LoanInput(
            request_id=uuid4(),
            employee_id=employee,
            amount=D("10000"),
            issued_on=date(2026, 12, 4),
            due_on=date(2026, 12, 6),
            reason="Проверочный заём",
        ),
    )
    issue = await fund_ledger.new_operation(
        session, lead, operation("loan_issue", basket, employee_id=employee, loan_id=loan.id)
    )
    await fund_ledger.confirm_operation(session, lead, issue.id)
    await session.commit()
    clock.freeze(datetime(2026, 12, 7, 7, 1, tzinfo=UTC))
    bot = AsyncMock()
    assert await send_fund_notifications(bot, maker) == 1
    assert "Срок возврата займа" in bot.send_message.call_args.args[1]
    clock.freeze(datetime(2026, 12, 8, 7, 1, tzinfo=UTC))
    assert await send_fund_notifications(bot, maker) == 0
    assert bot.send_message.call_count == 1


async def test_bot_transfer_wizard_offers_other_basket_and_posts_once(session, team):
    lead, _, _, first, second = team
    await link(session, lead, 901)
    row = await fund_bot.create_draft(session, 901, "operation", MONTH)
    target = next(f for f in row.payload["fields"] if f["name"] == "target_basket_id")
    assert str(second) in target["options"]
    answers = ["transfer", str(first), "1000", "2026-12-04", str(lead), str(second), "0", "Перевод"]
    for index, value in enumerate(answers):
        await fund_bot.answer(session, 901, row.id, value, f"operation:{index}")
    await fund_bot.submit(session, 901, row.id)
    await fund_bot.submit(session, 901, row.id)
    from teamtime.db.fund_operations import FundOperation

    operation_row = await session.scalar(
        select(FundOperation).where(FundOperation.kind == "transfer")
    )
    assert operation_row is not None
    assert await fund_ledger.balance(session, "cash", first) == D("100000")
    await fund_ledger.confirm_operation(session, lead, operation_row.id)
    assert await fund_ledger.balance(session, "cash", first) == D("99000")
    assert await fund_ledger.balance(session, "cash", second) == D("51000")


async def test_backup_failure_alert_is_once_even_after_network_timeout(
    session, maker, team, monkeypatch
):
    from contextlib import asynccontextmanager

    from teamtime.core.config import Settings
    from teamtime.services.fund_backup import alert_failure

    lead = team[0]
    await link(session, lead, 901)
    await session.commit()
    bot = AsyncMock()
    bot.send_message.side_effect = TimeoutError
    monkeypatch.setattr("aiogram.Bot", lambda *args, **kwargs: bot)
    monkeypatch.setattr("teamtime.bot.app._session", lambda _: None)
    monkeypatch.setattr(
        "teamtime.core.config.get_settings",
        lambda: Settings(_env_file=None, demo=False, bot_token="123456:fictional-test-token"),
    )

    @asynccontextmanager
    async def scope():
        async with maker() as isolated:
            yield isolated
            await isolated.commit()

    monkeypatch.setattr("teamtime.db.session.session_scope", scope)
    await alert_failure("test-backup-cycle")
    await alert_failure("test-backup-cycle")
    assert bot.send_message.call_count == 1
    stored = await session.scalar(
        select(FundNotification).where(FundNotification.cycle == "backup-error:test-backup-cycle")
    )
    assert stored.error == "TimeoutError"
