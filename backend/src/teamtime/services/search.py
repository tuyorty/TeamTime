"""Поиск для командной палитры: люди, дни, задачи."""

from __future__ import annotations

import re
from datetime import date

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from teamtime.db.models import Daily, DailyTask, Employee, SchedulePlan, SprintTask
from teamtime.parsing.text import fold
from teamtime.schemas import SearchHit, SearchOut
from teamtime.services.reports import MONTHS_GENITIVE

_DATE = re.compile(r"^(\d{1,2})[./](\d{1,2})(?:[./](\d{2,4}))?$")


async def search(session: AsyncSession, query: str, today: date, limit: int = 12) -> SearchOut:
    q = query.strip()
    hits: list[SearchHit] = []
    if not q:
        return SearchOut(query=q, hits=hits)

    if m := _DATE.match(q):
        d, mo, y = int(m[1]), int(m[2]), m[3]
        year = (int(y) + 2000 if len(y) == 2 else int(y)) if y else today.year
        try:
            day = date(year, mo, d)
        except ValueError:
            day = None
        if day:
            iso = day.isocalendar()
            hits.append(
                SearchHit(
                    kind="day",
                    title=f"{day.day} {MONTHS_GENITIVE[day.month - 1]} {day.year}",
                    subtitle=f"{iso.week} неделя",
                    href=f"/week/{iso.year}/{iso.week}?day={day.isoformat()}",
                )
            )

    needle = f"%{q}%"
    employees = await session.scalars(
        select(Employee)
        .where(
            or_(
                Employee.full_name.ilike(needle),
                Employee.short_name.ilike(needle),
                Employee.position.ilike(needle),
                Employee.match_key.like(f"%{fold(q)}%"),
            )
        )
        .order_by(Employee.short_name)
        .limit(limit)
    )
    hits.extend(
        SearchHit(
            kind="employee",
            title=e.full_name,
            subtitle=e.position or e.short_name,
            href=f"/people/{e.id}",
        )
        for e in employees
    )

    if len(q) >= 3:
        done = await session.execute(
            select(DailyTask.text, Daily.work_date, Employee.short_name, Employee.id)
            .join(Daily, DailyTask.daily_id == Daily.id)
            .join(Employee, Daily.employee_id == Employee.id)
            .where(Daily.retracted_at.is_(None), DailyTask.text.ilike(needle))
            .order_by(Daily.work_date.desc())
            .limit(limit)
        )
        seen: set[tuple[str, int]] = set()
        for text, day, name, emp_id in done:
            if (text, emp_id) in seen:
                continue
            seen.add((text, emp_id))
            iso = day.isocalendar()
            hits.append(
                SearchHit(
                    kind="task",
                    title=text,
                    subtitle=f"{name}, {day:%d.%m.%Y}",
                    href=f"/week/{iso.year}/{iso.week}?day={day.isoformat()}&e={emp_id}",
                )
            )
        planned = await session.execute(
            select(
                SprintTask.text, SchedulePlan.iso_year, SchedulePlan.iso_week, Employee.short_name
            )
            .join(SchedulePlan, SprintTask.plan_id == SchedulePlan.id)
            .join(Employee, SchedulePlan.employee_id == Employee.id)
            .where(SchedulePlan.retracted_at.is_(None), SprintTask.text.ilike(needle))
            .order_by(SchedulePlan.week_start.desc())
            .limit(limit)
        )
        for text, year, week, name in planned:
            if (text, -week) in seen:
                continue
            seen.add((text, -week))
            hits.append(
                SearchHit(
                    kind="task",
                    title=text,
                    subtitle=f"Спринт, {name}, {week} неделя",
                    href=f"/plans/{year}/{week}",
                )
            )
    return SearchOut(query=q, hits=hits[: limit * 2])
