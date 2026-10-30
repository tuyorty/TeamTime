"""Заявки на статусы, история условий и состояние системы."""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from teamtime.api.deps import AdminDep, AdminReadDep, AppSettingsDep, SessionDep
from teamtime.db.models import (
    CalculationVersion,
    EmployeeTerms,
    NotificationPreference,
    StatusRequest,
)
from teamtime.schemas import EmployeeBrief, Schema
from teamtime.services import diagnostics, manual, status_requests

router = APIRouter(tags=["экраны"])


class StatusRequestOut(Schema):
    id: int
    employee_id: int
    employee: EmployeeBrief
    start: date
    end: date
    kind: str | None
    note: str
    state: str
    created_at: datetime
    decided_at: datetime | None
    decision_note: str


class StatusRequestsOut(BaseModel):
    items: list[StatusRequestOut]
    total: int
    pending: int


class DecisionIn(BaseModel):
    accepted: bool
    note: str = Field("", max_length=500)


@router.get("/admin/status-requests", summary="Заявки сотрудников на статусы")
async def requests(
    session: SessionDep,
    _: AdminReadDep,
    state: Literal["pending", "accepted", "rejected", "all"] = "pending",
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
) -> StatusRequestsOut:
    query = select(StatusRequest)
    if state != "all":
        query = query.where(StatusRequest.state == state)
    total = await session.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = await session.scalars(
        query.options(selectinload(StatusRequest.employee))
        .order_by(StatusRequest.created_at, StatusRequest.id)
        .offset(offset)
        .limit(limit)
    )
    pending = (
        await session.scalar(
            select(func.count()).select_from(StatusRequest).where(StatusRequest.state == "pending")
        )
        or 0
    )
    return StatusRequestsOut(
        items=[StatusRequestOut.model_validate(row) for row in rows], total=total, pending=pending
    )


@router.post(
    "/admin/status-requests/{request_id}/decision", summary="Согласовать или отклонить заявку"
)
async def decide_status(
    request_id: int, body: DecisionIn, session: SessionDep, actor: AdminDep
) -> StatusRequestOut:
    try:
        row = await status_requests.decide(session, request_id, body.accepted, actor, body.note)
    except manual.EditError as exc:
        raise HTTPException(409, str(exc)) from exc
    await session.refresh(row, ["employee"])
    return StatusRequestOut.model_validate(row)


class NotificationIn(BaseModel):
    enabled: bool = True
    delay_minutes: int | None = Field(None, ge=1, le=240)
    quiet_start: int | None = Field(None, ge=0, le=1439)
    quiet_end: int | None = Field(None, ge=0, le=1439)

    @model_validator(mode="after")
    def valid_quiet(self) -> NotificationIn:
        if (self.quiet_start is None) != (self.quiet_end is None) or (
            self.quiet_start is not None and self.quiet_start == self.quiet_end
        ):
            raise ValueError("Укажите начало и конец тихого времени; они должны различаться")
        return self


class NotificationOut(NotificationIn):
    employee_id: int


@router.get("/admin/notifications/{employee_id}", summary="Личные настройки уведомлений")
async def notification_preferences(
    employee_id: int, session: SessionDep, _: AdminReadDep
) -> NotificationOut:
    row = await session.get(NotificationPreference, employee_id)
    return NotificationOut(
        employee_id=employee_id,
        **({key: getattr(row, key) for key in NotificationIn.model_fields} if row else {}),
    )


@router.put("/admin/notifications/{employee_id}", summary="Изменить уведомления сотрудника")
async def update_notifications(
    employee_id: int, body: NotificationIn, session: SessionDep, actor: AdminDep
) -> NotificationOut:
    from teamtime.services.notifications import save_preferences

    try:
        row = await save_preferences(session, employee_id, body.model_dump(), actor)
    except manual.EditError as exc:
        raise HTTPException(422, str(exc)) from exc
    return NotificationOut(
        employee_id=employee_id, **{key: getattr(row, key) for key in NotificationIn.model_fields}
    )


class TermsOut(Schema):
    effective_from: date
    monthly_norm_minutes: int
    hourly_rate: str


class HistoryOut(BaseModel):
    calculations: list[dict[str, Any]]
    terms: list[dict[str, Any]]


@router.get("/admin/calculation-history", summary="Сохранённые версии правил, норм и ставок")
async def calculation_history(session: SessionDep, _: AdminReadDep) -> HistoryOut:
    versions = await session.scalars(
        select(CalculationVersion).order_by(CalculationVersion.effective_from.desc())
    )
    terms = await session.scalars(
        select(EmployeeTerms).order_by(
            EmployeeTerms.effective_from.desc(), EmployeeTerms.employee_id
        )
    )
    return HistoryOut(
        calculations=[
            {"effective_from": row.effective_from.isoformat(), "value": row.value}
            for row in versions
        ],
        terms=[
            {
                "employee_id": row.employee_id,
                "effective_from": row.effective_from.isoformat(),
                "monthly_norm_minutes": row.monthly_norm_minutes,
                "hourly_rate": str(row.hourly_rate),
            }
            for row in terms
        ],
    )


@router.get("/admin/system", summary="Состояние бота, доставки, личек и бэкапа")
async def system_state(
    session: SessionDep, settings: AppSettingsDep, _: AdminReadDep
) -> diagnostics.SystemOut:
    return await diagnostics.system_state(session, settings)
