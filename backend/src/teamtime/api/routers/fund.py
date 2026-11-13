"""Единый финансовый раздел: расчёт, журнал, согласование и настройка фонда."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from itertools import pairwise
from typing import Any, Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from teamtime.api.deps import AdminDep, ConfigDep, SessionDep
from teamtime.api.fund_deps import IdentityDep, LeaderDep, MemberDep, WriterDep, require_module
from teamtime.calc.fund_time import Calendar
from teamtime.db.fund import FundAudit, FundCalendar, FundMember, FundPeriod, FundTerms
from teamtime.db.fund_operations import (
    FundAdjustment,
    FundAttachment,
    FundClaim,
    FundLoan,
    FundOpening,
    FundOperation,
    FundPosting,
    FundTimeRequest,
)
from teamtime.db.models import Employee
from teamtime.fund_schemas import (
    Amount,
    BasketInput,
    BonusInput,
    CalendarInput,
    ClaimInput,
    CloseInput,
    CorrectionInput,
    DecisionInput,
    Input,
    LoanInput,
    MemberInput,
    OpeningInput,
    OperationInput,
    ReceiptInput,
    ReconciliationInput,
    SourceInput,
    TermsInput,
    TimeRequestInput,
    VacationYearInput,
)
from teamtime.services import (
    export,
    fund_changes,
    fund_config,
    fund_corrections,
    fund_report,
    fund_requests,
    fund_setup,
)
from teamtime.services import (
    fund as inputs,
)
from teamtime.services import (
    fund_ledger as ledger,
)

router = APIRouter(prefix="/fund", tags=["фонд"], dependencies=[Depends(require_module)])


class WorkIntervalInput(Input):
    start: int = Field(ge=0, lt=86400)
    end: int = Field(ge=0, le=86400)
    efficiency: int = Field(ge=0, le=100)


class WorkFactInput(Input):
    day: date
    intervals: list[WorkIntervalInput] = Field(min_length=1, max_length=24)
    reason: str = Field(min_length=1, max_length=1000)


@router.post("/members/{employee_id}/work")
async def set_work(
    employee_id: int, body: WorkFactInput, session: SessionDep, actor: LeaderDep
) -> dict[str, int]:
    from teamtime.calc.fund import split_interval
    from teamtime.services import manual

    await inputs.lock(session)
    await inputs.member(session, employee_id)
    ranges = sorted(
        (day, start, end)
        for interval in body.intervals
        for day, start, end in split_interval(body.day, interval.start, interval.end)
    )
    if any(a[0] == b[0] and a[2] > b[1] for a, b in pairwise(ranges)):
        raise inputs.FundError("Рабочие интервалы пересекаются", 422)
    try:
        daily = await manual.set_daily(
            session,
            employee_id=employee_id,
            work_date=body.day,
            intervals=[(i.start, i.end) for i in body.intervals],
            efficiency=None,
            interval_efficiencies=[i.efficiency for i in body.intervals],
            actor=f"employee:{actor.employee_id}",
            reason=body.reason,
        )
    except manual.EditError as exc:
        raise inputs.FundError(str(exc), 422) from exc
    return {"daily_id": daily.id}


class VacationAdjustmentInput(Input):
    expected_adjustment: int
    adjustment: int = Field(ge=-3660, le=3660)
    reason: str = Field(min_length=1, max_length=1000)


@router.post("/vacations/{year_id}/adjust")
async def adjust_vacation(
    year_id: int, body: VacationAdjustmentInput, session: SessionDep, actor: LeaderDep
) -> dict[str, int]:
    from teamtime.db.fund_operations import FundVacationYear

    await inputs.lock(session)
    year = await session.get(FundVacationYear, year_id, populate_existing=True)
    if year is None:
        raise inputs.FundError("Отпускной год не найден", 404)
    if year.adjustment_days != body.expected_adjustment:
        raise inputs.FundError("Остаток уже изменён; обновите данные")
    before = year.adjustment_days
    year.adjustment_days = body.adjustment
    balances = await fund_requests.vacation_balance(session, year.employee_id)
    if any(b["id"] == year.id and b["available"] < 0 for b in balances):
        raise inputs.FundError("Корректировка перекрывает уже согласованный отпуск")
    ledger.audit(
        session,
        actor.employee_id,
        "vacation.adjusted",
        id=year.id,
        before=before,
        after=year.adjustment_days,
        reason=body.reason,
    )
    return {"adjustment_days": year.adjustment_days}


def fields(row: Any, names: str) -> dict[str, Any]:
    return {name: getattr(row, name) for name in names.split()}


@router.get("/setup")
async def setup(session: SessionDep, actor: IdentityDep) -> dict[str, Any]:
    config = await fund_config.load(session)
    count = await session.scalar(select(func.count()).select_from(FundMember))
    return {
        "enabled": config.enabled,
        "first_month": config.first_month,
        "needs_bootstrap": not count,
        "employees": [
            fields(e, "id full_name short_name department is_active")
            for e in await session.scalars(select(Employee).order_by(Employee.id))
        ],
    }


class BootstrapInput(BaseModel):
    joined_on: date


@router.post("/bootstrap")
async def bootstrap(
    body: BootstrapInput, session: SessionDep, actor: IdentityDep, technical: AdminDep
) -> dict[str, int]:
    row = await fund_setup.bootstrap(session, actor.employee_id, body.joined_on)
    return {"employee_id": row.employee_id}


@router.post("/activate")
async def activate(body: BootstrapInput, session: SessionDep, actor: LeaderDep) -> dict[str, Any]:
    return (await fund_setup.activate(session, actor.employee_id, body.joined_on)).model_dump(
        mode="json"
    )


class Preferences(BaseModel):
    notification_hour: int = Field(ge=0, le=23)
    notification_minute: int = Field(ge=0, le=59)
    reminders_enabled: bool
    technical_employee_ids: list[int] = Field(max_length=10)


@router.post("/preferences")
async def preferences(body: Preferences, session: SessionDep, actor: LeaderDep) -> dict[str, Any]:
    await inputs.lock(session)
    for employee_id in body.technical_employee_ids:
        await inputs.member(session, employee_id)
    config = await fund_config.load(session)
    config = config.model_copy(update=body.model_dump())
    await fund_config.save(session, config)
    ledger.audit(session, actor.employee_id, "preferences.changed", **body.model_dump())
    return config.model_dump(mode="json")


@router.get("/overview")
async def overview(session: SessionDep, actor: MemberDep) -> dict[str, Any]:
    treasury = await ledger.treasury(session, actor.employee_id)
    members = []
    for person in await session.scalars(select(FundMember).order_by(FundMember.employee_id)):
        employee = await session.get(Employee, person.employee_id)
        if employee:
            opening = await session.get(FundOpening, person.employee_id)
            members.append(
                {
                    **fields(employee, "id full_name short_name department avatar_url"),
                    **fields(person, "active leader joined_on left_on"),
                    "overpayment": str(
                        await ledger.balance(session, "overpayment", person.employee_id)
                    ),
                    "unallocated": str(
                        await ledger.balance(session, "unallocated", person.employee_id)
                    ),
                    "opening": fields(opening, "month amount reason") if opening else None,
                }
            )
    operations = [
        fields(
            o,
            "id kind state occurred_on amount basket_id target_basket_id employee_id details "
            "reason created_by created_at confirmed_by confirmed_at consented_at reverses_id",
        )
        for o in await session.scalars(
            select(FundOperation)
            .order_by(FundOperation.created_at.desc(), FundOperation.id.desc())
            .limit(500)
        )
    ]
    claims = [
        fields(
            c,
            "id employee_id month spent_on amount title state decided_by decided_at "
            "decision_reason created_at",
        )
        for c in await session.scalars(select(FundClaim).order_by(FundClaim.id.desc()).limit(500))
    ]
    adjustments = [
        fields(
            a,
            "id employee_id kind origin_month applied_month amount before after reason state "
            "created_by approved_by approved_at",
        )
        for a in await session.scalars(
            select(FundAdjustment).order_by(FundAdjustment.id.desc()).limit(500)
        )
    ]
    requests = []
    for row in await session.scalars(
        select(FundTimeRequest).order_by(FundTimeRequest.id.desc()).limit(500)
    ):
        item = fields(
            row, "id employee_id kind days seconds state decided_by decided_at decision_reason"
        )
        item["reason"] = (
            row.reason
            if actor.leader or actor.employee_id == row.employee_id
            else "Запрос сотрудника"
        )
        if not actor.leader and actor.employee_id != row.employee_id:
            item["decision_reason"] = "Решение руководителя" if row.decided_at else ""
        requests.append(item)
    loans = []
    from teamtime.core import clock
    from teamtime.services.settings import load_settings

    today = clock.now().astimezone((await load_settings(session)).tz).date()
    for loan in await session.scalars(select(FundLoan).order_by(FundLoan.id.desc())):
        outstanding = await ledger.balance(session, "loan", loan.id)
        loans.append(
            {
                **fields(loan, "id employee_id amount issued_on due_on reason issued approved_by"),
                "outstanding": str(outstanding),
                "overdue": loan.issued and outstanding > 0 and loan.due_on < today,
            }
        )
    calendars = [
        fields(c, "id month version source source_version days holidays reason created_by")
        for c in await session.scalars(
            select(FundCalendar)
            .order_by(FundCalendar.month.desc(), FundCalendar.version.desc())
            .limit(60)
        )
    ]
    terms = [
        fields(
            t,
            "id employee_id effective_from revision target share sources no_other_income "
            "reason created_by",
        )
        for t in await session.scalars(
            select(FundTerms).order_by(FundTerms.effective_from.desc(), FundTerms.revision.desc())
        )
    ]
    history = []
    for entry in await session.scalars(select(FundAudit).order_by(FundAudit.id.desc()).limit(200)):
        item = fields(entry, "id actor_id action data created_at")
        if not actor.leader and entry.action.startswith(("time.", "vacation.")):
            item["data"] = {k: v for k, v in entry.data.items() if k != "reason"}
        history.append(item)
    return {
        **treasury,
        "members": members,
        "operations": operations,
        "claims": claims,
        "loans": loans,
        "requests": requests,
        "adjustments": adjustments,
        "calendars": calendars,
        "terms": terms,
        "history": history,
        "closed_changes": await fund_changes.pending(session),
        "periods": [
            fields(p, "month closed_at closed_by")
            for p in await session.scalars(select(FundPeriod).order_by(FundPeriod.month.desc()))
        ],
        "config": (await fund_config.load(session)).model_dump(mode="json"),
    }


@router.get("/months/{month}")
async def month_report(month: date, session: SessionDep, actor: MemberDep) -> dict[str, Any]:
    return await fund_report.report(session, actor.employee_id, month)


@router.post("/months/{month}/close")
async def close(
    month: date, body: CloseInput, session: SessionDep, actor: LeaderDep
) -> dict[str, Any]:
    return await fund_report.close_month(
        session, actor.employee_id, month, body.fingerprint, body.reason
    )


@router.put("/members")
async def set_member(
    body: MemberInput, session: SessionDep, actor: LeaderDep, config: ConfigDep
) -> dict[str, int]:
    return {
        "employee_id": (
            await fund_setup.set_member(session, actor.employee_id, body, demo=config.demo)
        ).employee_id
    }


@router.post("/members/{employee_id}/terms")
async def set_terms(
    employee_id: int, body: TermsInput, session: SessionDep, actor: LeaderDep
) -> dict[str, int]:
    return {
        "id": (
            await inputs.put_terms(session, actor.employee_id, employee_id, **body.model_dump())
        ).id
    }


@router.post("/members/{employee_id}/opening")
async def set_opening(
    employee_id: int, body: OpeningInput, session: SessionDep, actor: LeaderDep
) -> dict[str, int]:
    return {
        "employee_id": (
            await fund_setup.overpayment_opening(session, actor.employee_id, employee_id, body)
        ).employee_id
    }


@router.post("/calendars")
async def set_calendar(
    body: CalendarInput, session: SessionDep, actor: LeaderDep
) -> dict[str, int]:
    cal = Calendar(body.month, body.version, body.source, body.days, frozenset(body.holidays))
    return {"id": (await inputs.put_calendar(session, actor.employee_id, cal, body.reason)).id}


@router.post("/receipts")
async def receipt(body: ReceiptInput, session: SessionDep, actor: WriterDep) -> dict[str, Any]:
    row = await inputs.add_receipt(
        session, actor.employee_id, actor.employee_id, **body.model_dump()
    )
    return fields(row, "id source amount origin_month applied_month received_on")


@router.post("/sources/confirm")
async def confirm_source(
    body: SourceInput, session: SessionDep, actor: WriterDep
) -> dict[str, Any]:
    row = await inputs.confirm_source(
        session, actor.employee_id, actor.employee_id, **body.model_dump()
    )
    return fields(row, "source month version complete confirmed_total")


@router.post("/baskets")
async def basket(body: BasketInput, session: SessionDep, actor: LeaderDep) -> dict[str, int]:
    return {"id": (await fund_setup.add_basket(session, actor.employee_id, body)).id}


class BasketOpening(BaseModel):
    as_of: date
    amount: Amount
    reason: str = Field(min_length=1, max_length=1000)


@router.post("/baskets/{basket_id}/opening")
async def basket_opening(
    basket_id: int, body: BasketOpening, session: SessionDep, actor: WriterDep
) -> dict[str, bool]:
    await fund_setup.basket_opening(
        session, actor.employee_id, basket_id, body.as_of, body.amount, body.reason
    )
    return {"ok": True}


@router.post("/operations")
async def new_operation(
    body: OperationInput, session: SessionDep, actor: WriterDep
) -> dict[str, Any]:
    return fields(
        await ledger.new_operation(session, actor.employee_id, body), "id state kind amount"
    )


@router.post("/operations/{operation_id}/confirm")
async def confirm_operation(
    operation_id: int, session: SessionDep, actor: WriterDep
) -> dict[str, Any]:
    return fields(
        await ledger.confirm_operation(session, actor.employee_id, operation_id), "id state"
    )


@router.post("/operations/{operation_id}/consent")
async def consent(operation_id: int, session: SessionDep, actor: WriterDep) -> dict[str, Any]:
    return fields(await ledger.consent(session, actor.employee_id, operation_id), "id consented_at")


class Reason(BaseModel):
    reason: str = Field(min_length=1, max_length=1000)


@router.post("/closed-changes/{event_id}/review")
async def review_closed_change(
    event_id: int, body: Reason, session: SessionDep, actor: LeaderDep
) -> dict[str, bool]:
    await fund_changes.reviewed(session, actor.employee_id, event_id, body.reason)
    return {"reviewed": True}


@router.post("/operations/{operation_id}/cancel")
async def cancel_operation(
    operation_id: int, body: Reason, session: SessionDep, actor: WriterDep
) -> dict[str, Any]:
    return fields(
        await ledger.cancel_operation(session, actor.employee_id, operation_id, body.reason),
        "id state",
    )


@router.post("/operations/{operation_id}/reverse")
async def reverse_operation(
    operation_id: int, body: Reason, session: SessionDep, actor: WriterDep
) -> dict[str, Any]:
    return fields(
        await ledger.reverse_operation(session, actor.employee_id, operation_id, body.reason),
        "id state",
    )


@router.post("/reconciliations")
async def reconciliation(
    body: ReconciliationInput, session: SessionDep, actor: WriterDep
) -> dict[str, Any]:
    return fields(
        await ledger.reconcile(session, actor.employee_id, body), "id actual expected as_of"
    )


@router.post("/claims")
async def new_claim(body: ClaimInput, session: SessionDep, actor: WriterDep) -> dict[str, int]:
    return {"id": (await fund_requests.new_claim(session, actor.employee_id, body)).id}


@router.post("/claims/{claim_id}/decide")
async def decide_claim(
    claim_id: int, body: DecisionInput, session: SessionDep, actor: LeaderDep
) -> dict[str, Any]:
    return fields(
        await fund_requests.decide_claim(session, actor.employee_id, claim_id, body), "id state"
    )


@router.post("/claims/{claim_id}/attachment")
async def upload(
    claim_id: int, request: Request, session: SessionDep, actor: WriterDep
) -> dict[str, int]:
    claim = await session.get(FundClaim, claim_id)
    if claim is None or claim.employee_id != actor.employee_id:
        raise HTTPException(403, "Вложение добавляет автор заявки")
    data = bytearray()
    async for chunk in request.stream():
        data.extend(chunk)
        if len(data) > 10 * 1024 * 1024:
            raise HTTPException(413, "Вложение не больше 10 МБ")
    mime = (
        "application/pdf"
        if data.startswith(b"%PDF-")
        else "image/png"
        if data.startswith(b"\x89PNG\r\n\x1a\n")
        else "image/jpeg"
        if data.startswith(b"\xff\xd8\xff")
        else None
    )
    if mime is None:
        raise HTTPException(422, "Поддерживаются PDF, PNG и JPEG")
    for existing in await session.scalars(
        select(FundAttachment).where(FundAttachment.claim_id == claim_id)
    ):
        if existing.data == bytes(data):
            return {"id": existing.id}
    filename = request.query_params.get("name", f"receipt-{claim_id}")
    filename = filename.replace("\\", "/").split("/")[-1][:100]
    row = FundAttachment(
        claim_id=claim_id,
        owner_id=actor.employee_id,
        name=filename or f"receipt-{claim_id}",
        content_type=mime,
        data=bytes(data),
    )
    session.add(row)
    await session.flush()
    return {"id": row.id}


@router.get("/claims/{claim_id}/attachments")
async def attachments(claim_id: int, session: SessionDep, actor: MemberDep) -> list[dict[str, Any]]:
    claim = await session.get(FundClaim, claim_id)
    if claim is None or not (actor.leader or claim.employee_id == actor.employee_id):
        raise HTTPException(403, "Исходный чек доступен автору и руководителю")
    return [
        fields(a, "id name content_type created_at")
        for a in await session.scalars(
            select(FundAttachment).where(FundAttachment.claim_id == claim_id)
        )
    ]


@router.get("/attachments/{attachment_id}")
async def attachment(attachment_id: int, session: SessionDep, actor: MemberDep) -> Response:
    row = await session.get(FundAttachment, attachment_id)
    if row is None or not (actor.leader or row.owner_id == actor.employee_id):
        raise HTTPException(403, "Исходный чек доступен автору и руководителю")
    return Response(
        row.data,
        media_type=row.content_type,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(row.name)}",
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.post("/loans")
async def loan(body: LoanInput, session: SessionDep, actor: LeaderDep) -> dict[str, int]:
    return {"id": (await ledger.approve_loan(session, actor.employee_id, body)).id}


@router.post("/time-requests/{employee_id}")
async def time_request(
    employee_id: int, body: TimeRequestInput, session: SessionDep, actor: WriterDep
) -> dict[str, int]:
    return {
        "id": (
            await fund_requests.new_time_request(session, actor.employee_id, employee_id, body)
        ).id
    }


@router.post("/time-requests/{request_id}/decide")
async def decide_time(
    request_id: int, body: DecisionInput, session: SessionDep, actor: LeaderDep
) -> dict[str, Any]:
    return fields(
        await fund_requests.decide_time_request(session, actor.employee_id, request_id, body),
        "id state",
    )


@router.post("/time-requests/{request_id}/cancel")
async def cancel_time(
    request_id: int, body: Reason, session: SessionDep, actor: LeaderDep
) -> dict[str, Any]:
    return fields(
        await fund_requests.cancel_time_request(
            session, actor.employee_id, request_id, body.reason
        ),
        "id state",
    )


@router.get("/vacations/{employee_id}")
async def vacations(
    employee_id: int, session: SessionDep, actor: MemberDep
) -> list[dict[str, Any]]:
    return await fund_requests.vacation_balance(session, employee_id)


@router.post("/vacations")
async def vacation_year(
    body: VacationYearInput, session: SessionDep, actor: LeaderDep
) -> dict[str, int]:
    return {"id": (await fund_requests.set_vacation_year(session, actor.employee_id, body)).id}


@router.post("/bonuses")
async def bonus(body: BonusInput, session: SessionDep, actor: LeaderDep) -> dict[str, int]:
    return {"id": (await fund_corrections.bonus(session, actor.employee_id, body)).id}


@router.post("/corrections")
async def correction(
    body: CorrectionInput, session: SessionDep, actor: WriterDep
) -> dict[str, Any]:
    return fields(
        await fund_corrections.propose(session, actor.employee_id, body),
        "id kind amount before after state applied_month",
    )


@router.post("/corrections/{adjustment_id}/decide")
async def decide_correction(
    adjustment_id: int, body: DecisionInput, session: SessionDep, actor: LeaderDep
) -> dict[str, Any]:
    return fields(
        await fund_corrections.decide(session, actor.employee_id, adjustment_id, body),
        "id state amount applied_month",
    )


@router.get("/members/{employee_id}/overpayment-history")
async def overpayment_history(
    employee_id: int, session: SessionDep, actor: MemberDep
) -> list[dict[str, Any]]:
    rows = await session.execute(
        select(FundPosting, FundOperation)
        .join(FundOperation)
        .where(
            FundPosting.account == "overpayment",
            FundPosting.account_id == employee_id,
        )
        .order_by(FundOperation.occurred_on, FundOperation.id)
    )
    return [
        {
            "operation_id": o.id,
            "date": o.occurred_on,
            "kind": o.kind,
            "amount": p.amount,
            "reason": o.reason,
            "confirmed_by": o.confirmed_by,
            "details": o.details,
        }
        for p, o in rows
    ]


@router.get("/export/{month}.{fmt}")
async def download(
    month: date,
    fmt: Literal["csv", "xlsx"],
    session: SessionDep,
    actor: MemberDep,
    employee_id: list[int] | None = Query(None),
) -> Response:
    report = await fund_report.report(session, actor.employee_id, month)
    header = [
        "Сотрудник",
        "Отдел",
        "Норма",
        "Эффективные часы",
        "Штраф",
        "Зачтено",
        "Расчётная зарплата",
        "Премии",
        "Корректировки",
        "Получено из источников",
        "Переплата входящая",
        "Зачтено переплаты",
        "Переплата новая",
        "Переплата остаток",
        "Доплата фонда",
        "Округление",
        "Компенсации",
        "Начислено фондом",
        "Выплачено",
        "Осталось",
        "Статус",
    ]
    rows = []
    for row in report["rows"]:
        if employee_id is not None and row["employee"]["id"] not in employee_id:
            continue
        a = row["amounts"] or {}
        rows.append(
            [
                row["employee"]["name"],
                row["employee"]["department"],
                *(
                    export.Duration(row[k])
                    for k in ("norm_sec", "effective_sec", "penalty_sec", "credited_sec")
                ),
                *(
                    Decimal(a[k]) if k in a else None
                    for k in (
                        "salary",
                        "bonus",
                        "correction",
                        "received",
                        "overpayment_in",
                        "offset",
                        "overpayment_new",
                        "overpayment_out",
                        "supplement",
                        "rounding",
                        "compensation",
                        "accrued",
                        "paid",
                        "due",
                    )
                ),
                "Закрыт" if report["closed"] else "Предварительный",
            ]
        )
    content = (
        export.to_csv(header, rows)
        if fmt == "csv"
        else export.to_xlsx([("Расчёт фонда", header, rows)])
    )
    from teamtime.api.routers.export import _file

    return _file(content, fmt, f"fund-{month:%Y-%m}")
