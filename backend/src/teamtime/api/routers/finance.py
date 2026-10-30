"""Расчёт оплаты и администраторские премии за проекты."""

from datetime import date
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, HTTPException, Path, Query
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field, field_validator

from teamtime.api.deps import AdminDep, AppSettingsDep, SessionDep
from teamtime.api.routers.export import Fmt, _file
from teamtime.schemas import FinanceOut, ProjectBonusOut
from teamtime.services import export, finance

router = APIRouter(tags=["финансы"])
Year = Annotated[int, Path(ge=2000, le=2100)]
Month = Annotated[int, Path(ge=1, le=12)]


class BonusValues(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    title: str = Field(min_length=1, max_length=200)
    amount: Decimal = Field(gt=0, le=Decimal("1000000000"), max_digits=12, decimal_places=2)
    note: str = Field("", max_length=1000)


class BonusCreate(BonusValues):
    request_id: UUID
    employee_id: int = Field(gt=0)
    month: date

    @field_validator("month")
    @classmethod
    def validate_month(cls, value: date) -> date:
        if value.day != 1 or not 2000 <= value.year <= 2100:
            raise ValueError("Укажите первый день месяца в диапазоне 2000–2100")
        return value


class BonusEdit(BonusValues):
    version: int = Field(ge=1)


class BonusCancel(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    version: int = Field(ge=1)
    reason: str = Field(min_length=1, max_length=500)


@router.get("/finances/{year}/{month}", summary="Оклад, переработки и проектные премии за месяц")
async def report(
    session: SessionDep, settings: AppSettingsDep, year: Year, month: Month
) -> FinanceOut:
    return await finance.report(session, settings, year, month)


@router.post("/admin/bonuses", summary="Добавить премию за проект")
async def create_bonus(body: BonusCreate, session: SessionDep, actor: AdminDep) -> ProjectBonusOut:
    try:
        row = await finance.add_bonus(
            session, actor, **{**body.model_dump(), "request_id": str(body.request_id)}
        )
    except finance.FinanceError as exc:
        raise HTTPException(exc.status, str(exc)) from exc
    return ProjectBonusOut.model_validate(row)


@router.put("/admin/bonuses/{bonus_id}", summary="Исправить сумму или описание премии")
async def edit_bonus(
    bonus_id: int, body: BonusEdit, session: SessionDep, actor: AdminDep
) -> ProjectBonusOut:
    try:
        row = await finance.edit_bonus(session, bonus_id, actor=actor, **body.model_dump())
    except finance.FinanceError as exc:
        raise HTTPException(exc.status, str(exc)) from exc
    return ProjectBonusOut.model_validate(row)


@router.post("/admin/bonuses/{bonus_id}/cancel", summary="Отменить премию с сохранением истории")
async def cancel_bonus(
    bonus_id: int, body: BonusCancel, session: SessionDep, actor: AdminDep
) -> ProjectBonusOut:
    try:
        row = await finance.edit_bonus(
            session, bonus_id, body.version, actor, cancel_reason=body.reason
        )
    except finance.FinanceError as exc:
        raise HTTPException(exc.status, str(exc)) from exc
    return ProjectBonusOut.model_validate(row)


@router.get("/export/finances/{year}/{month}.{fmt}", summary="Расчёт оплаты в Excel или CSV")
async def download(
    session: SessionDep,
    settings: AppSettingsDep,
    year: Year,
    month: Month,
    fmt: Fmt,
    employee_id: Annotated[list[int] | None, Query()] = None,
) -> Response:
    data = await finance.report(session, settings, year, month, employee_id)
    header = [
        "Сотрудник",
        "Ставка, ₽/ч",
        "Норма",
        "Зачтено",
        "Оклад, ₽",
        "Переработка",
        "За переработку, ₽",
        "Проектные премии, ₽",
        "Итого, ₽",
    ]
    rows = [
        [
            r.employee.full_name,
            r.summary.hourly_rate,
            export.Duration(r.summary.norm_sec),
            export.Duration(r.summary.total_sec),
            r.amounts.salary,
            export.Duration(r.summary.overtime_sec),
            r.amounts.overtime_pay,
            r.amounts.project_bonuses,
            r.amounts.total,
        ]
        for r in data.rows
    ]
    rows.append(
        [
            "Всего",
            None,
            None,
            None,
            data.totals.salary,
            None,
            data.totals.overtime_pay,
            data.totals.project_bonuses,
            data.totals.total,
        ]
    )
    if fmt == "csv":
        content = export.to_csv(header, rows)
    else:
        bonuses = [
            [
                r.employee.full_name,
                b.month,
                b.title,
                b.amount,
                b.note,
                "Отменена" if b.cancelled_at else "Учтена",
                b.cancel_reason,
            ]
            for r in data.rows
            for b in r.bonuses
        ]
        content = export.to_xlsx(
            [
                ("Расчёт оплаты", header, rows),
                (
                    "Проектные премии",
                    [
                        "Сотрудник",
                        "Месяц",
                        "Проект / основание",
                        "Сумма, ₽",
                        "Комментарий",
                        "Состояние",
                        "Причина отмены",
                    ],
                    bonuses,
                ),
                (
                    "Правила",
                    ["Показатель", "Расчёт"],
                    [
                        ["Период", data.label],
                        ["Итоги", "Промежуточные" if not data.complete else "За завершённый месяц"],
                        ["Оклад", "Норма × ставка. Недоработка не уменьшает оклад."],
                        [
                            "Переработка",
                            "max(0, зачтённые часы − норма) × ставка. "
                            "Часы с учётом эффективности и штрафа за опоздания.",
                        ],
                        [
                            "Итого",
                            "Оклад + переработки + действующие проектные премии. "
                            "Фактические выплаты не учитываются.",
                        ],
                    ],
                ),
            ]
        )
    return _file(content, fmt, f"xtime-finance-{year}-{month:02d}")
