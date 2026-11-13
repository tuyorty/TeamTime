"""Подтверждаемые финансовые черновики из лички. Сеть и расчёты отделены от проведения."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID, uuid4

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from teamtime.core import clock
from teamtime.db.fund_operations import FundBasket
from teamtime.db.models import BotDraft, Employee
from teamtime.fund_schemas import (
    BonusInput,
    ClaimInput,
    CorrectionInput,
    DecisionInput,
    LoanInput,
    OperationInput,
    ReceiptInput,
    ReconciliationInput,
    TimeRequestInput,
)
from teamtime.services import fund, fund_corrections, fund_ledger, fund_report, fund_requests
from teamtime.services.settings import load_settings


def field(name: str, label: str, kind: str = "text", **kwargs: Any) -> dict[str, Any]:
    return {"name": name, "label": label, "kind": kind, **kwargs}


async def create_draft(
    session: AsyncSession,
    user: int,
    action: str,
    month: date,
    reference: int = 0,
) -> BotDraft:
    person = await fund.telegram_member(session, user)
    employee = person.employee_id
    today = clock.now().astimezone((await load_settings(session)).tz).date()
    amount = field("amount", "Сумма на руки, ₽", "money")
    reason = field("reason", "Основание или комментарий")
    day = field("date", "Дата факта: ГГГГ-ММ-ДД", "date", default=str(today))
    fields: list[dict[str, Any]] = []
    values: dict[str, Any] = {"month": str(month), "reference": reference}
    if action == "receipt":
        report = await fund_report.report(session, employee, month)
        row = next((r for r in report["rows"] if r["employee"]["id"] == employee), None)
        fields = [
            field(
                "source",
                "От какого источника получена выплата?",
                options=[s["name"] for s in row["sources"]] if row else [],
            ),
            amount,
            day,
        ]
    elif action == "claim":
        fields = [field("title", "На что потрачены свои деньги?"), amount, day]
    elif action == "time":
        fields = [
            field(
                "kind",
                "Что согласовать?",
                options={
                    "vacation": "Отпуск",
                    "sick": "Больничный",
                    "trip": "Командировка",
                    "waiver": "Уважительное опоздание",
                    "no_work": "День без работы",
                },
            ),
            field("start", "Первая дата: ГГГГ-ММ-ДД", "date"),
            field("end", "Последняя дата включительно: ГГГГ-ММ-ДД", "date"),
            field(
                "minutes", "Сколько минут опоздания исключить? Для отсутствия укажите 0", "integer"
            ),
            reason,
        ]
    elif action in {
        "claim_decide",
        "time_decide",
        "correction_decide",
        "operation_cancel",
        "operation_reverse",
    }:
        if action.endswith("decide"):
            await fund.member(session, employee, leader=True)
            fields.append(
                field("approve", "Решение", options={"yes": "Подтвердить", "no": "Отклонить"})
            )
        fields.append(reason)
    elif action == "reconcile":
        owned_baskets = await session.scalars(
            select(FundBasket).where(FundBasket.owner_id == employee, FundBasket.active)
        )
        fields = [
            field(
                "basket_id",
                "Какую корзину сверяем?",
                "integer",
                options={str(b.id): b.name for b in owned_baskets},
            ),
            field("actual", "Фактический остаток, ₽ (включая 0)", "money_zero"),
            day,
            reason,
        ]
    elif action == "correction":
        fields = [
            field(
                "kind",
                "Что исправляем?",
                options={
                    "salary": "Часы закрытого месяца",
                    "source": "Полученную выплату",
                    "compensation": "Компенсации закрытого месяца",
                },
            ),
            field(
                "reference_id",
                "Номер поступления для исправления источника; для других исправлений — 0",
                "integer",
            ),
            field(
                "corrected_amount",
                "Правильная сумма, ₽. Для пересчёта часов введите «пересчитать»",
                "corrected",
            ),
            reason,
        ]
    elif action in {"bonus", "loan", "operation"}:
        people = list(await session.scalars(select(Employee).order_by(Employee.id)))
        person_field = field(
            "employee_id", "Участник", "integer", options={str(p.id): p.short_name for p in people}
        )
        if action in {"bonus", "loan"}:
            await fund.member(session, employee, leader=True)
            fields = [person_field, amount]
            if action == "loan":
                fields += [
                    day,
                    field("due_on", "Вернуть до: ГГГГ-ММ-ДД, максимум два месяца", "date"),
                ]
            fields.append(reason)
        else:
            baskets = list(await session.scalars(select(FundBasket).where(FundBasket.active)))
            choices = {str(b.id): b.name for b in baskets if b.owner_id == employee}
            if not choices:
                raise fund.FundError("Операции с деньгами подтверждают ответственные за корзины")
            fields = [
                field(
                    "kind",
                    "Вид операции",
                    options={
                        "contribution": "Взнос",
                        "interest": "Проценты",
                        "expense": "Расход фонда",
                        "payment": "Выплата сотруднику",
                        "transfer": "Между корзинами",
                        "loan_issue": "Выдача займа",
                        "loan_repayment": "Возврат займа",
                        "overpayment_return": "Возврат переплаты",
                    },
                ),
                field("basket_id", "Корзина", "integer", options=choices),
                amount,
                day,
                person_field,
                field(
                    "target_basket_id",
                    "Корзина назначения для перевода; иначе 0",
                    "integer",
                    options={"0": "Не перевод", **{str(b.id): b.name for b in baskets}},
                ),
                field(
                    "reference_id",
                    "Номер обязательства для выплаты или займа для выдачи/возврата; иначе 0",
                    "integer",
                ),
                reason,
            ]
    else:
        raise fund.FundError("Неизвестное действие", 422)
    row = BotDraft(
        id=str(uuid4()),
        employee_id=employee,
        user_id=user,
        payload={
            "type": "fund",
            "action": action,
            "fields": fields,
            "values": values,
            "step": 0,
            "seen": [],
        },
    )
    session.add(row)
    await session.flush()
    return row


async def owned_draft(session: AsyncSession, user: int, draft_id: str) -> BotDraft:
    person = await fund.telegram_member(session, user)
    row = await session.scalar(select(BotDraft).where(BotDraft.id == draft_id).with_for_update())
    if (
        row is None
        or row.user_id != user
        or row.employee_id != person.employee_id
        or row.payload.get("type") != "fund"
    ):
        raise fund.FundError("Черновик не найден или принадлежит другому участнику", 403)
    return row


def parse_value(step: dict[str, Any], text: str) -> Any:
    text = text.strip()
    if not text or len(text) > 1000:
        raise fund.FundError("Введите непустой ответ, не длиннее 1000 символов", 422)
    options = step.get("options")
    if isinstance(options, dict) and text not in options:
        raise fund.FundError("Выберите один из вариантов кнопками", 422)
    try:
        match step["kind"]:
            case "date":
                return date.fromisoformat(text).isoformat()
            case "integer":
                integer_value = int(text)
                if integer_value < 0:
                    raise ValueError
                return integer_value
            case "money" | "money_zero" | "corrected":
                if step["kind"] == "corrected" and text.casefold() == "пересчитать":
                    return None
                value = Decimal(text.replace(" ", "").replace("\u00a0", "").replace(",", "."))
                if (
                    not value.is_finite()
                    or value < 0
                    or value != value.quantize(Decimal(".01"))
                    or value > Decimal("999999999999.99")
                    or (step["kind"] == "money" and value == 0)
                ):
                    raise ValueError
                return str(value)
            case _:
                return text
    except (ValueError, InvalidOperation) as exc:
        raise fund.FundError(
            "Проверьте формат ответа; сумма — в рублях с точностью до копеек", 422
        ) from exc


async def answer(
    session: AsyncSession, user: int, draft_id: str, text: str, event_id: str
) -> BotDraft:
    row = await owned_draft(session, user, draft_id)
    payload = row.payload
    if row.submitted_at or event_id in payload["seen"] or payload["step"] >= len(payload["fields"]):
        return row
    step = payload["fields"][payload["step"]]
    value = parse_value(step, text)
    values = {**payload["values"], step["name"]: value}
    next_step = payload["step"] + 1
    while next_step < len(payload["fields"]) and payload["fields"][next_step]["name"] in values:
        next_step += 1
    row.payload = {
        **payload,
        "step": next_step,
        "values": values,
        "seen": [*payload["seen"], event_id],
    }
    await session.flush()
    return row


async def submit(session: AsyncSession, user: int, draft_id: str) -> tuple[BotDraft, str]:
    await fund.lock(session)
    row = await owned_draft(session, user, draft_id)
    if row.submitted_at:
        return row, str(row.payload["result"])
    p = row.payload
    if p["step"] != len(p["fields"]):
        raise fund.FundError("Сначала заполните все поля")
    v, actor, request_id = p["values"], row.employee_id, UUID(row.id)
    month = date.fromisoformat(v["month"])
    action = p["action"]
    try:
        if action == "receipt":
            body = ReceiptInput(
                request_id=request_id,
                source=v["source"],
                origin_month=month,
                received_on=v["date"],
                amount=v["amount"],
            )
            result = await fund.add_receipt(session, actor, actor, **body.model_dump())
            message = (
                f"Поступление #{result.id} сохранено: {result.amount} "
                f"₽. Учтено за {result.applied_month:%m.%Y}."
            )
        elif action == "claim":
            claim = await fund_requests.new_claim(
                session,
                actor,
                ClaimInput(
                    request_id=request_id,
                    month=month,
                    spent_on=v["date"],
                    amount=v["amount"],
                    title=v["title"],
                ),
            )
            message = f"Расход #{claim.id} отправлен на согласование: {claim.amount} ₽."
        elif action == "time":
            start, end = date.fromisoformat(v["start"]), date.fromisoformat(v["end"])
            if not 0 <= (end - start).days <= 365:
                raise fund.FundError("Проверьте границы периода", 422)
            days = [start + timedelta(days=i) for i in range((end - start).days + 1)]
            time_request = await fund_requests.new_time_request(
                session,
                actor,
                actor,
                TimeRequestInput(
                    request_id=request_id,
                    kind=v["kind"],
                    days=days,
                    seconds=v["minutes"] * 60,
                    reason=v["reason"],
                ),
            )
            message = (
                f"Запрос #{time_request.id} отправлен руководителю. До решения расчёт не меняется."
            )
        elif action == "reconcile":
            await fund_ledger.reconcile(
                session,
                actor,
                ReconciliationInput(
                    request_id=request_id,
                    basket_id=v["basket_id"],
                    as_of=v["date"],
                    actual=v["actual"],
                    reason=v["reason"],
                ),
            )
            message = "Фактический остаток сохранён для сверки. Движение денег не создавалось."
        elif action == "bonus":
            bonus = await fund_corrections.bonus(
                session,
                actor,
                BonusInput(
                    request_id=request_id,
                    employee_id=v["employee_id"],
                    month=month,
                    amount=v["amount"],
                    reason=v["reason"],
                ),
            )
            message = f"Премия #{bonus.id} подтверждена: {bonus.amount} ₽."
        elif action == "loan":
            loan = await fund_ledger.approve_loan(
                session,
                actor,
                LoanInput(
                    request_id=request_id,
                    employee_id=v["employee_id"],
                    amount=v["amount"],
                    issued_on=v["date"],
                    due_on=v["due_on"],
                    reason=v["reason"],
                ),
            )
            message = (
                f"Заём #{loan.id} одобрен. Выдачу денег должен подтвердить "
                f"ответственный за корзину."
            )
        elif action == "operation":
            kind = v["kind"]
            operation = await fund_ledger.new_operation(
                session,
                actor,
                OperationInput(
                    request_id=request_id,
                    kind=kind,
                    amount=v["amount"],
                    occurred_on=v["date"],
                    basket_id=v["basket_id"],
                    target_basket_id=v["target_basket_id"] if kind == "transfer" else None,
                    employee_id=v["employee_id"]
                    if kind in {"payment", "loan_issue", "loan_repayment", "overpayment_return"}
                    else None,
                    loan_id=v["reference_id"] if kind.startswith("loan_") else None,
                    allocations=[{"obligation_id": v["reference_id"], "amount": v["amount"]}]
                    if kind == "payment" and v["reference_id"]
                    else [],
                    reason=v["reason"],
                ),
            )
            message = (
                f"Операция #{operation.id} подготовлена. Подтвердите "
                f"факт движения денег в разделе «Операции»."
            )
        elif action == "correction":
            correction = await fund_corrections.propose(
                session,
                actor,
                CorrectionInput(
                    request_id=request_id,
                    employee_id=actor,
                    origin_month=month,
                    kind=v["kind"],
                    corrected_amount=v["corrected_amount"],
                    reference_id=v["reference_id"] or None,
                    reason=v["reason"],
                ),
            )
            message = (
                f"Корректировка #{correction.id}: {correction.amount:+.2f} "
                f"₽. Ожидает решения руководителя."
            )
        elif action.endswith("_decide"):
            functions = {
                "claim_decide": fund_requests.decide_claim,
                "time_decide": fund_requests.decide_time_request,
                "correction_decide": fund_corrections.decide,
            }
            await functions[action](
                session,
                actor,
                v["reference"],
                DecisionInput(approve=v["approve"] == "yes", reason=v["reason"]),
            )
            message = "Решение сохранено."
        elif action == "operation_cancel":
            await fund_ledger.cancel_operation(session, actor, v["reference"], v["reason"])
            message = "Черновик отменён."
        elif action == "operation_reverse":
            await fund_ledger.reverse_operation(session, actor, v["reference"], v["reason"])
            message = "Обратная операция проведена; исходный факт сохранён в истории."
        else:
            raise fund.FundError("Неизвестное действие", 422)
    except ValidationError as exc:
        raise fund.FundError(
            "Проверьте поля: " + "; ".join(str(e["msg"]) for e in exc.errors()), 422
        ) from exc
    row.submitted_at = clock.now()
    row.payload = {**p, "result": message}
    await session.flush()
    return row, message
