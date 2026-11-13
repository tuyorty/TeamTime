"""Сравнение расписания и предварительный расчёт последствий одобрения без записи в БД."""

from __future__ import annotations

from collections import Counter
from datetime import timedelta

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from teamtime.db.models import ParseResultRow, SchedulePlan, Source
from teamtime.schemas import PlanOut, ScheduleChangePreview, ScheduleDayChange
from teamtime.services.facts import date_range, load_cells
from teamtime.services.reports import cell_out, plan_out
from teamtime.services.settings import AppSettings


def _same_plan(left: PlanOut | None, right: PlanOut | None) -> bool:
    if left is None or right is None:
        return left is right
    return (
        left.kind == right.kind
        and left.intervals == right.intervals
        and (left.note or None) == (right.note or None)
    )


async def schedule_change_preview(
    session: AsyncSession, row: ParseResultRow, settings: AppSettings
) -> ScheduleChangePreview | None:
    plan = await session.scalar(
        select(SchedulePlan)
        .where(
            SchedulePlan.parse_result_id == row.id,
            SchedulePlan.source != Source.MANUAL,
        )
        .order_by(SchedulePlan.version.desc())
        .limit(1)
        .options(
            selectinload(SchedulePlan.days),
            selectinload(SchedulePlan.tasks),
        )
    )
    if plan is None:
        return None
    previous = await session.scalar(
        select(SchedulePlan)
        .where(
            SchedulePlan.employee_id == plan.employee_id,
            SchedulePlan.iso_year == plan.iso_year,
            SchedulePlan.iso_week == plan.iso_week,
            SchedulePlan.version < plan.version,
            or_(
                SchedulePlan.source_version_id.is_(None),
                SchedulePlan.source_version_id != plan.source_version_id,
            ),
        )
        .order_by(SchedulePlan.version.desc())
        .limit(1)
        .options(
            selectinload(SchedulePlan.days),
            selectinload(SchedulePlan.tasks),
        )
    )
    start, end = plan.week_start, plan.week_start + timedelta(days=6)
    current = await load_cells(session, settings, start, end, [plan.employee_id])
    accepted = await load_cells(
        session,
        settings,
        start,
        end,
        [plan.employee_id],
        extra_approved=[plan.id],
        extra_restored=[plan.id],
    )
    old_days = {day.date: plan_out(day) for day in previous.days} if previous else {}
    new_days = {day.date: plan_out(day) for day in plan.days}
    days = []
    for day in date_range(start, end):
        current_cell = current[(plan.employee_id, day)]
        accepted_cell = accepted[(plan.employee_id, day)]
        before, after = (
            cell_out(current_cell),
            cell_out(accepted_cell),
        )
        affects = not _same_plan(before.plan, after.plan) or before.late_sec != after.late_sec
        approval_note = None
        if (
            not affects
            and current_cell.plan is not None
            and current_cell.plan.source is Source.MANUAL
            and accepted_cell.plan is not None
            and accepted_cell.plan.id == current_cell.plan.id
            and not _same_plan(before.plan, new_days.get(day))
        ):
            approval_note = (
                "После этой версии расписание исправлено вручную. Одобрение сообщения "
                "не заменит ручной план; при необходимости измените день в таблице."
            )
        if not _same_plan(old_days.get(day), new_days.get(day)) or affects:
            days.append(
                ScheduleDayChange(
                    date=day,
                    previous=old_days.get(day),
                    submitted=new_days.get(day),
                    current=before,
                    if_accepted=after,
                    affects_calculation=affects,
                    approval_note=approval_note,
                )
            )
    old_tasks = [task.text for task in previous.tasks] if previous else []
    new_tasks = [task.text for task in plan.tasks]
    return ScheduleChangePreview(
        plan_id=plan.id,
        version=plan.version,
        previous_version=previous.version if previous else None,
        late_change=any(issue["code"] == "late_change" for issue in row.issues),
        days=days,
        tasks_added=list((Counter(new_tasks) - Counter(old_tasks)).elements()),
        tasks_removed=list((Counter(old_tasks) - Counter(new_tasks)).elements()),
    )
