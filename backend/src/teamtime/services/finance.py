"""Оклад за норму, переработки по ставке и ручные премии. Факт выплат не ведётся."""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from teamtime.calc.month import MonthSummary, overtime_bonus
from teamtime.core import clock
from teamtime.db.models import Employee, ProjectBonus
from teamtime.schemas import FinanceAmounts, FinanceOut, FinanceRow, ProjectBonusOut
from teamtime.services import audit, events, reports
from teamtime.services.facts import date_range, employees_for_period, load_cells, today_local
from teamtime.services.history import settings_at, terms_at
from teamtime.services.settings import AppSettings


class FinanceError(ValueError):
    def __init__(self, message: str, status: int = 409):
        super().__init__(message)
        self.status = status


def amounts(summary: MonthSummary, bonus: Decimal) -> FinanceAmounts:
    """Недоработка не уменьшает оклад; эффективность и опоздания влияют на переработку."""
    salary = overtime_bonus(summary.norm, summary.hourly_rate)
    return FinanceAmounts(
        salary=salary,
        overtime_pay=summary.bonus,
        project_bonuses=bonus,
        total=salary + summary.bonus + bonus,
    )


async def report(
    session: AsyncSession,
    settings: AppSettings,
    year: int,
    month: int,
    employee_ids: list[int] | None = None,
) -> FinanceOut:
    first, last = reports.month_bounds(year, month)
    bonuses = list(
        await session.scalars(
            select(ProjectBonus)
            .where(ProjectBonus.month == first)
            .order_by(ProjectBonus.created_at.desc(), ProjectBonus.id.desc())
        )
    )
    employees = {e.id: e for e in await employees_for_period(session, first, last)}
    # Премии бывших сотрудников остаются видны даже без дейликов за месяц.
    missing_ids = {b.employee_id for b in bonuses} - employees.keys()
    if missing_ids:
        employees.update(
            {
                e.id: e
                for e in await session.scalars(select(Employee).where(Employee.id.in_(missing_ids)))
            }
        )
    selected = sorted(
        (e for e in employees.values() if employee_ids is None or e.id in employee_ids),
        key=lambda e: (e.short_name, e.id),
    )
    ids = [e.id for e in selected]
    cells = await load_cells(session, settings, first, last, ids)
    terms = await terms_at(session, ids, first)
    rules = await settings_at(session, settings, first)
    grouped: dict[int, list[ProjectBonus]] = defaultdict(list)
    for bonus in bonuses:
        grouped[bonus.employee_id].append(bonus)
    rows = []
    for employee in selected:
        summary = reports.summarize(
            employee,
            [cells[(employee.id, d)] for d in date_range(first, last)],
            rules,
            terms.get(employee.id),
        )
        eb = grouped[employee.id]
        rows.append(
            FinanceRow(
                employee=reports.brief(employee),
                summary=reports.summary_out(summary),
                amounts=amounts(
                    summary, sum((b.amount for b in eb if b.cancelled_at is None), Decimal("0.00"))
                ),
                bonuses=[ProjectBonusOut.model_validate(b) for b in eb],
            )
        )
    return FinanceOut(
        year=year,
        month=month,
        label=reports.month_label(year, month),
        complete=today_local(settings) > last,
        rows=rows,
        totals=FinanceAmounts(
            **{
                key: sum((getattr(r.amounts, key) for r in rows), Decimal("0.00"))
                for key in FinanceAmounts.model_fields
            }
        ),
    )


def snapshot(row: ProjectBonus) -> dict[str, Any]:
    return ProjectBonusOut.model_validate(row).model_dump(mode="json")


async def changed(
    session: AsyncSession,
    row: ProjectBonus,
    actor: str,
    action: str,
    before: dict[str, Any] | None = None,
) -> None:
    await session.flush()
    await audit.record(
        session,
        actor=actor,
        action=action,
        entity_type="project_bonus",
        entity_id=row.id,
        employee_id=row.employee_id,
        before=before,
        after=snapshot(row),
    )
    await events.notify(
        session, "finance.changed", employee_id=row.employee_id, dates=[row.month.isoformat()]
    )


async def add_bonus(
    session: AsyncSession,
    actor: str,
    *,
    request_id: str,
    employee_id: int,
    month: date,
    title: str,
    amount: Decimal,
    note: str,
) -> ProjectBonus:
    if await session.get(Employee, employee_id) is None:
        raise FinanceError("Сотрудник не найден", 404)
    values = {
        "request_id": request_id,
        "employee_id": employee_id,
        "month": month,
        "title": title,
        "amount": amount,
        "note": note,
        "created_by": actor,
    }
    row_id = await session.scalar(
        insert(ProjectBonus)
        .values(**values)
        .on_conflict_do_nothing(index_elements=[ProjectBonus.request_id])
        .returning(ProjectBonus.id)
    )
    row = await session.scalar(select(ProjectBonus).where(ProjectBonus.request_id == request_id))
    assert row is not None
    if row_id is None:
        if row.cancelled_at or any(getattr(row, key) != value for key, value in values.items()):
            raise FinanceError("Эта премия уже сохранена с другими данными. Обновите страницу.")
        return row
    await changed(session, row, actor, "bonus.created")
    return row


async def edit_bonus(
    session: AsyncSession,
    bonus_id: int,
    version: int,
    actor: str,
    *,
    title: str | None = None,
    amount: Decimal | None = None,
    note: str = "",
    cancel_reason: str | None = None,
) -> ProjectBonus:
    row = await session.scalar(
        select(ProjectBonus).where(ProjectBonus.id == bonus_id).with_for_update()
    )
    if row is None:
        raise FinanceError("Премия не найдена", 404)
    if row.version != version or row.cancelled_at is not None:
        raise FinanceError("Премия уже изменена. Обновите данные перед сохранением.")
    before = snapshot(row)
    if cancel_reason is not None:
        row.cancelled_at = clock.now()
        row.cancel_reason = cancel_reason
    else:
        assert title is not None
        assert amount is not None
        row.title, row.amount, row.note = title, amount, note
    row.version += 1
    await changed(
        session,
        row,
        actor,
        "bonus.cancelled" if cancel_reason is not None else "bonus.updated",
        before,
    )
    return row
