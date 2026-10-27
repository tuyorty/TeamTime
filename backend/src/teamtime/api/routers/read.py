"""Чтение: открыто всем в локальной сети без входа (ADR 0006)."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Annotated

from fastapi import APIRouter, HTTPException, Path, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from teamtime import __version__
from teamtime.api.deps import AppSettingsDep, ConfigDep, IsAdminDep, SessionDep
from teamtime.core import clock
from teamtime.db.models import AuditLog, Employee, TelegramIdentity
from teamtime.parsing import MessageKind
from teamtime.schemas import (
    AuditOut,
    DayCellOut,
    EmployeeDetailOut,
    EmployeeOut,
    IdentityOut,
    InboxOut,
    MessageOut,
    MetaOut,
    MonthOut,
    PlansOut,
    SearchOut,
    TodayOut,
    WeekOut,
)
from teamtime.services import messages, reports
from teamtime.services.facts import active_employees, date_range, load_cells, today_local
from teamtime.services.search import search as run_search

router = APIRouter()


def _check_week(iso_year: int, iso_week: int) -> None:
    try:
        date.fromisocalendar(iso_year, iso_week, 1)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Нет такой ISO-недели") from exc


@router.get("/meta", tags=["служебное"], summary="Параметры сайта и текущая дата команды")
async def meta(settings: AppSettingsDep, config: ConfigDep, admin: IsAdminDep) -> MetaOut:
    return MetaOut(
        version=__version__,
        demo=config.demo,
        admin_enabled=config.admin_enabled,
        is_admin=admin,
        timezone=settings.timezone,
        today=today_local(settings),
        now=clock.now(),
        bot_username=config.bot_username,
        late_tolerance_min=settings.late_tolerance_min,
        weekly_off=settings.weekly_off,
    )


@router.get("/today", tags=["экраны"], summary="Сегодня: кто на месте, опоздания, дейлики, лента")
async def today(session: SessionDep, settings: AppSettingsDep, day: date | None = None) -> TodayOut:
    return await reports.today_report(session, settings, day)


@router.get(
    "/weeks/{iso_year}/{iso_week}",
    tags=["экраны"],
    summary="Неделя: матрица сотрудники × дни (замена Google-таблицы)",
)
async def week(
    session: SessionDep, settings: AppSettingsDep, iso_year: int, iso_week: int
) -> WeekOut:
    _check_week(iso_year, iso_week)
    return await reports.week_report(session, settings, iso_year, iso_week)


@router.get("/months/{year}/{month}", tags=["экраны"], summary="Месяц: итог, опоздания, премии")
async def month(
    session: SessionDep,
    settings: AppSettingsDep,
    year: Annotated[int, Path(ge=2000, le=2100)],
    month: Annotated[int, Path(ge=1, le=12)],
    history: Annotated[int, Query(ge=1, le=12)] = 6,
) -> MonthOut:
    return await reports.month_report(session, settings, year, month, history=history)


@router.get("/plans/{iso_year}/{iso_week}", tags=["экраны"], summary="Планы недели и их версии")
async def plans(
    session: SessionDep, settings: AppSettingsDep, iso_year: int, iso_week: int
) -> PlansOut:
    _check_week(iso_year, iso_week)
    return await reports.plans_report(session, settings, iso_year, iso_week)


@router.get("/calendar", tags=["экраны"], summary="Календарь команды: ячейки за диапазон")
async def team_calendar(
    session: SessionDep,
    settings: AppSettingsDep,
    start: date,
    end: date,
) -> dict[int, list[DayCellOut]]:
    if end < start or (end - start).days > 62:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Диапазон от 1 до 62 дней")
    employees = await active_employees(session)
    cells = await load_cells(session, settings, start, end, [e.id for e in employees])
    return {
        e.id: [reports.cell_out(cells[(e.id, d)]) for d in date_range(start, end)]
        for e in employees
    }


@router.get("/employees", tags=["сотрудники"], summary="Справочник сотрудников")
async def employees(session: SessionDep, include_inactive: bool = False) -> list[EmployeeOut]:
    rows = await active_employees(session, include_inactive=include_inactive)
    return [EmployeeOut.model_validate(e) for e in rows]


@router.get(
    "/employees/{employee_id}", tags=["сотрудники"], summary="Карточка сотрудника и статистика"
)
async def employee(
    session: SessionDep,
    settings: AppSettingsDep,
    employee_id: int,
    start: date | None = None,
    end: date | None = None,
) -> EmployeeDetailOut:
    e = await session.get(Employee, employee_id)
    if e is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Сотрудник не найден")
    if start and end and (end < start or end - start > timedelta(days=370)):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Диапазон до года")
    return await reports.employee_report(session, settings, e, start, end)


@router.get("/identities", tags=["сотрудники"], summary="Аккаунты Telegram и привязки")
async def identities(session: SessionDep) -> list[IdentityOut]:
    rows = await session.scalars(
        select(TelegramIdentity)
        .order_by(TelegramIdentity.employee_id.is_not(None), TelegramIdentity.last_seen_at.desc())
        .options(
            selectinload(TelegramIdentity.employee),
            selectinload(TelegramIdentity.suggested_employee),
        )
    )
    return [IdentityOut.model_validate(i) for i in rows]


@router.get(
    "/messages/{raw_id}", tags=["сообщения"], summary="Исходное сообщение: версии и разборы"
)
async def message(session: SessionDep, raw_id: int) -> MessageOut:
    out = await messages.message_out(session, raw_id)
    if out is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Сообщение не найдено")
    return out


@router.get("/inbox", tags=["сообщения"], summary="Инбокс: что требует решения")
async def inbox(
    session: SessionDep,
    view: Annotated[str, Query(pattern="^(pending|resolved|auto)$")] = "pending",
    employee: Annotated[
        str | None, Query(pattern=r"^(\d+|none)$", description="id сотрудника или none")
    ] = None,
    problem: Annotated[str | None, Query(pattern="^(failed|partial|unlinked)$")] = None,
    kind: Annotated[MessageKind | None, Query()] = None,
) -> InboxOut:
    return await messages.inbox(
        session,
        view,
        employee=int(employee) if employee and employee.isdigit() else None,
        unlinked=employee == "none",
        problem=problem,
        kind=kind,
    )


@router.get("/search", tags=["служебное"], summary="Поиск по людям, дням и задачам")
async def search(session: SessionDep, settings: AppSettingsDep, q: str = "") -> SearchOut:
    return await run_search(session, q[:100], today_local(settings))


class PenaltyPreviewOut(BaseModel):
    late_sec: int
    penalty_sec: int


@router.get("/penalty", tags=["экраны"], summary="Калькулятор штрафа: сумма опозданий → штраф")
async def penalty(
    settings: AppSettingsDep, late_minutes: Annotated[int, Query(ge=0, le=100 * 60)] = 0
) -> PenaltyPreviewOut:
    value = settings.penalty.scale().penalty(late_minutes * 60)
    return PenaltyPreviewOut(late_sec=late_minutes * 60, penalty_sec=int(value))


@router.get("/audit", tags=["служебное"], summary="Журнал правок")
async def audit(
    session: SessionDep,
    employee_id: int | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    before_id: int | None = None,
) -> list[AuditOut]:
    q = select(AuditLog).order_by(AuditLog.id.desc()).limit(limit)
    if employee_id is not None:
        q = q.where(AuditLog.employee_id == employee_id)
    if before_id is not None:
        q = q.where(AuditLog.id < before_id)
    return [AuditOut.model_validate(a) for a in await session.scalars(q)]
