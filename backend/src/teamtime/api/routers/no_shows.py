"""Подтверждённые невыходы: только администратор, с явной причиной и проверкой снимка плана."""

from datetime import date, datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from teamtime.api.deps import AdminDep, AppSettingsDep, SessionDep
from teamtime.services import no_shows

router = APIRouter(prefix="/admin/days", tags=["админка"])


class NoShowInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    expected_plan_id: int = Field(gt=0)
    expected_seconds: int = Field(gt=0)
    reason: str = Field(min_length=3, max_length=1000)


class CancelNoShowInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    expected_id: int = Field(gt=0)
    reason: str = Field(min_length=3, max_length=1000)


class NoShowOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    employee_id: int
    date: date
    plan_id: int
    seconds: int
    intervals: list[list[int]]
    reason: str
    created_by: str
    created_at: datetime
    retracted_at: datetime | None


@router.post("/{employee_id}/{day}/no-show", response_model=NoShowOut)
async def confirm_no_show(
    employee_id: int,
    day: date,
    body: NoShowInput,
    session: SessionDep,
    settings: AppSettingsDep,
    actor: AdminDep,
) -> NoShowOut:
    try:
        row = await no_shows.confirm(
            session, settings, employee_id=employee_id, day=day, actor=actor, **body.model_dump()
        )
    except no_shows.NoShowError as exc:
        raise HTTPException(exc.status, str(exc)) from exc
    return NoShowOut.model_validate(row)


@router.post("/{employee_id}/{day}/no-show/cancel", response_model=NoShowOut)
async def cancel_no_show(
    employee_id: int,
    day: date,
    body: CancelNoShowInput,
    session: SessionDep,
    actor: AdminDep,
) -> NoShowOut:
    try:
        row = await no_shows.cancel(
            session, employee_id=employee_id, day=day, actor=actor, **body.model_dump()
        )
    except no_shows.NoShowError as exc:
        raise HTTPException(exc.status, str(exc)) from exc
    return NoShowOut.model_validate(row)
