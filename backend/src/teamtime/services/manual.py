"""Ручные правки админа и сотрудника (через бота). Каждая правка — новая версия + аудит.

Исходные сообщения не трогаются: правка создаёт версию с ``source = manual``, а прошлая
версия остаётся в истории.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from teamtime.calc import StatusKind
from teamtime.core import clock
from teamtime.db.models import (
    Daily,
    DailyInterval,
    DailyTask,
    DayStatus,
    Employee,
    ParseResultRow,
    PlanDay,
    RawMessage,
    RawMessageVersion,
    Resolution,
    SchedulePlan,
    Source,
    SprintTask,
    TelegramIdentity,
)
from teamtime.parsing import Interval, PlanDayKind, person_key
from teamtime.parsing.schedule import NAME_RE
from teamtime.services import audit, events
from teamtime.services.facts import current_dailies, current_plans
from teamtime.services.ingest import IngestOutcome, interpret, next_version, retract_derived
from teamtime.services.settings import AppSettings


class EditError(ValueError):
    """Ошибка правки, текст показывается пользователю."""


class _Keep:
    """Маркер «оставить как в текущей версии»."""


KEEP = _Keep()


def _daily_snapshot(d: Daily | None) -> dict[str, Any] | None:
    if d is None:
        return None
    return {
        "version": d.version,
        "intervals": [[i.start_sec, i.end_sec] for i in d.intervals],
        "efficiency": d.efficiency,
        "tasks": [t.text for t in d.tasks],
    }


def _check_intervals(intervals: list[tuple[int, int]]) -> list[Interval]:
    if not intervals:
        raise EditError("Нужен хотя бы один интервал")
    result = []
    for a, b in intervals:
        if not (0 <= a < 86400 and 0 <= b <= 86400):
            raise EditError("Время должно быть в пределах суток")
        if a == b:
            raise EditError("Интервал нулевой длины")
        result.append(Interval(a, b))
    return result


async def current_daily(session: AsyncSession, employee_id: int, day: date) -> Daily | None:
    found = await current_dailies(session, day, day, [employee_id])
    return found[0] if found else None


async def set_daily(
    session: AsyncSession,
    *,
    employee_id: int,
    work_date: date,
    intervals: list[tuple[int, int]] | None = None,
    efficiency: int | _Keep | None = KEEP,
    tasks: list[str] | None = None,
    actor: str,
    reason: str = "",
    parse_result_id: int | None = None,
) -> Daily:
    """Новая ручная версия дейлика. Не переданные поля берутся из текущей версии."""
    previous = await current_daily(session, employee_id, work_date)
    if intervals is None:
        if previous is None:
            raise EditError("Дейлика за этот день нет: укажите интервалы")
        intervals = [(i.start_sec, i.end_sec) for i in previous.intervals]
    checked = _check_intervals(intervals)
    if isinstance(efficiency, _Keep):
        efficiency = previous.efficiency if previous else None
    if efficiency is not None and not 0 <= efficiency <= 100:
        raise EditError("Эффективность — от 0 до 100%")
    if tasks is None:
        tasks = [t.text for t in previous.tasks] if previous else []

    daily = Daily(
        employee_id=employee_id,
        work_date=work_date,
        version=await next_version(
            session, Daily, Daily.employee_id == employee_id, Daily.work_date == work_date
        ),
        efficiency=efficiency,
        source=Source.MANUAL,
        source_version_id=previous.source_version_id if previous else None,
        parse_result_id=parse_result_id or (previous.parse_result_id if previous else None),
        created_by=actor,
        sent_at=previous.sent_at if previous else None,
        intervals=[
            DailyInterval(position=n, start_sec=i.start, end_sec=i.end)
            for n, i in enumerate(checked)
        ],
        tasks=[DailyTask(position=n, text=t) for n, t in enumerate(tasks)],
    )
    session.add(daily)
    await session.flush()
    await audit.record(
        session,
        actor=actor,
        action="daily.set",
        entity_type="daily",
        entity_id=daily.id,
        employee_id=employee_id,
        before=_daily_snapshot(previous),
        after={"date": work_date.isoformat(), **(_daily_snapshot(daily) or {})},
        reason=reason,
    )
    await events.notify(
        session,
        "daily.changed",
        employee_id=employee_id,
        dates=[work_date.isoformat()],
        actor=actor,
    )
    return daily


async def retract_daily(
    session: AsyncSession, *, employee_id: int, work_date: date, actor: str, reason: str = ""
) -> None:
    previous = await current_daily(session, employee_id, work_date)
    if previous is None:
        raise EditError("Дейлика за этот день нет")
    previous.retracted_at = clock.now()
    await audit.record(
        session, actor=actor, action="daily.retract", entity_type="daily", entity_id=previous.id,
        employee_id=employee_id, before=_daily_snapshot(previous), after=None, reason=reason,
    )  # fmt: skip
    await events.notify(
        session, "daily.changed", employee_id=employee_id, dates=[work_date.isoformat()]
    )


async def set_plan_day(
    session: AsyncSession,
    *,
    employee_id: int,
    day: date,
    kind: PlanDayKind | None,
    intervals: list[tuple[int, int]] | None = None,
    note: str | None = None,
    actor: str,
    reason: str = "",
) -> SchedulePlan:
    """Новая ручная версия плана недели, где изменён один день. ``kind=None`` убирает день."""
    week_start = day - timedelta(days=day.weekday())
    iso = week_start.isocalendar()
    plans = await current_plans(session, week_start, week_start + timedelta(days=6), [employee_id])
    previous = next((p for p in plans if p.week_start == week_start), None)

    checked: list[Interval] = []
    if kind is PlanDayKind.WORK:
        checked = _check_intervals(intervals or [])

    def copy_day(d: PlanDay) -> PlanDay:
        return PlanDay(
            date=d.date, kind=d.kind, start_sec=d.start_sec, end_sec=d.end_sec,
            planned_sec=d.planned_sec, intervals=list(d.intervals), note=d.note,
            note_has_time=d.note_has_time, raw_line=d.raw_line,
        )  # fmt: skip

    days = [copy_day(d) for d in (previous.days if previous else []) if d.date != day]
    if kind is not None:
        days.append(
            PlanDay(
                date=day,
                kind=kind,
                start_sec=checked[0].start if checked else None,
                end_sec=checked[-1].end if checked else None,
                planned_sec=sum(i.duration for i in checked) if checked else None,
                intervals=[[i.start, i.end] for i in checked],
                note=note,
                note_has_time=False,
                raw_line="",
            )
        )
    days.sort(key=lambda d: d.date)
    plan = SchedulePlan(
        employee_id=employee_id,
        iso_year=iso.year,
        iso_week=iso.week,
        week_start=week_start,
        sprint_start=previous.sprint_start if previous else week_start,
        sprint_end=previous.sprint_end if previous else week_start + timedelta(days=5),
        version=await next_version(
            session,
            SchedulePlan,
            SchedulePlan.employee_id == employee_id,
            SchedulePlan.iso_year == iso.year,
            SchedulePlan.iso_week == iso.week,
        ),
        source=Source.MANUAL,
        source_version_id=previous.source_version_id if previous else None,
        parse_result_id=previous.parse_result_id if previous else None,
        created_by=actor,
        days=days,
        tasks=[
            SprintTask(position=t.position, text=t.text)
            for t in (previous.tasks if previous else [])
        ],
    )
    session.add(plan)
    await session.flush()
    before_day = next((d for d in (previous.days if previous else []) if d.date == day), None)
    await audit.record(
        session,
        actor=actor,
        action="plan_day.set",
        entity_type="schedule_plan",
        entity_id=plan.id,
        employee_id=employee_id,
        before={
            "date": day.isoformat(),
            "kind": before_day.kind.value,
            "intervals": before_day.intervals,
            "note": before_day.note,
        }
        if before_day
        else None,
        after={
            "date": day.isoformat(),
            "kind": kind.value if kind else None,
            "intervals": [[i.start, i.end] for i in checked],
            "note": note,
        },
        reason=reason,
    )
    await events.notify(session, "plan.changed", employee_id=employee_id, dates=[day.isoformat()])
    return plan


async def set_status(
    session: AsyncSession,
    *,
    employee_id: int,
    day: date,
    kind: StatusKind | None,
    note: str = "",
    actor: str,
    reason: str = "",
) -> DayStatus | None:
    """Поставить или снять статус дня. Прошлый статус отзывается, история остаётся."""
    previous = await session.scalar(
        select(DayStatus).where(
            DayStatus.employee_id == employee_id,
            DayStatus.date == day,
            DayStatus.retracted_at.is_(None),
        )
    )
    if previous is not None:
        previous.retracted_at = clock.now()
        await session.flush()
    status = None
    if kind is not None:
        status = DayStatus(
            employee_id=employee_id, date=day, kind=kind, note=note, created_by=actor
        )
        session.add(status)
        await session.flush()
    await audit.record(
        session,
        actor=actor,
        action="status.set" if kind else "status.clear",
        entity_type="day_status",
        entity_id=status.id if status else (previous.id if previous else ""),
        employee_id=employee_id,
        before={"date": day.isoformat(), "kind": previous.kind.value, "note": previous.note}
        if previous
        else None,
        after={"date": day.isoformat(), "kind": kind.value, "note": note} if kind else None,
        reason=reason,
    )
    await events.notify(session, "status.changed", employee_id=employee_id, dates=[day.isoformat()])
    return status


async def set_status_range(
    session: AsyncSession,
    *,
    employee_id: int,
    start: date,
    end: date,
    kind: StatusKind | None,
    note: str = "",
    actor: str,
    reason: str = "",
) -> int:
    if end < start:
        raise EditError("Конец периода раньше начала")
    if (end - start).days > 62:
        raise EditError("Период длиннее двух месяцев: разбейте на части")
    n = 0
    day = start
    while day <= end:
        await set_status(
            session,
            employee_id=employee_id,
            day=day,
            kind=kind,
            note=note,
            actor=actor,
            reason=reason,
        )
        day += timedelta(days=1)
        n += 1
    return n


# --- сотрудники ----------------------------------------------------------------------------


def short_name_key(short_name: str) -> str:
    m = NAME_RE.match(short_name.strip())
    if not m:
        raise EditError("Краткое имя должно быть как в расписании: «Иванов И.И.»")
    return person_key(m["surname"], m["i1"] + (m["i2"] or ""))


def _employee_snapshot(e: Employee) -> dict[str, Any]:
    return {
        "full_name": e.full_name,
        "short_name": e.short_name,
        "position": e.position,
        "monthly_norm_minutes": e.monthly_norm_minutes,
        "hourly_rate": str(e.hourly_rate),
        "color": e.color,
        "is_active": e.is_active,
    }


async def save_employee(
    session: AsyncSession, data: dict[str, Any], *, actor: str, employee: Employee | None = None
) -> Employee:
    key = short_name_key(data["short_name"])
    clash = await session.scalar(select(Employee).where(Employee.match_key == key))
    if clash is not None and (employee is None or clash.id != employee.id):
        raise EditError(f"Сотрудник с ключом «{data['short_name']}» уже есть: {clash.full_name}")
    before = _employee_snapshot(employee) if employee else None
    if employee is None:
        employee = Employee(match_key=key, **data)
        session.add(employee)
    else:
        for field, value in data.items():
            setattr(employee, field, value)
        employee.match_key = key
    await session.flush()
    await audit.record(
        session,
        actor=actor,
        action="employee.update" if before else "employee.create",
        entity_type="employee",
        entity_id=employee.id,
        employee_id=employee.id,
        before=before,
        after=_employee_snapshot(employee),
    )
    await events.notify(session, "employee.changed", employee_id=employee.id)
    return employee


@dataclass(slots=True)
class DeleteReport:
    dailies: int
    plans: int


async def delete_employee(session: AsyncSession, employee: Employee, *, actor: str) -> DeleteReport:
    """Удалить сотрудника вместе с его планами, дейликами и статусами дней.

    Исходные сообщения остаются: они неизменяемы. Привязанные аккаунты Telegram и разборы
    сообщений отвязываются (ON DELETE SET NULL), поэтому новые сообщения от этих людей снова
    попадут в инбокс. Удаляем одним запросом, чтобы каскады отработала сама база.
    """
    dailies = await session.scalar(
        select(func.count()).select_from(Daily).where(Daily.employee_id == employee.id)
    )
    plans = await session.scalar(
        select(func.count())
        .select_from(SchedulePlan)
        .where(SchedulePlan.employee_id == employee.id)
    )
    report = DeleteReport(dailies=dailies or 0, plans=plans or 0)
    await audit.record(
        session,
        actor=actor,
        action="employee.delete",
        entity_type="employee",
        entity_id=employee.id,
        before={**_employee_snapshot(employee), "dailies": report.dailies, "plans": report.plans},
    )
    employee_id = employee.id
    session.expunge(employee)
    await session.execute(delete(Employee).where(Employee.id == employee_id))
    await events.notify(session, "employee.changed", employee_id=employee_id)
    return report


# --- привязка аккаунтов и инбокс -----------------------------------------------------------


@dataclass(slots=True)
class ReprocessReport:
    reprocessed: int
    outcomes: list[IngestOutcome]


async def reprocess_author(
    session: AsyncSession, telegram_user_id: int, settings: AppSettings, *, actor: str
) -> ReprocessReport:
    """Переразобрать сообщения автора, ожидающие привязки сотрудника."""
    rows = await session.execute(
        select(RawMessage, RawMessageVersion)
        .join(RawMessageVersion, RawMessageVersion.raw_message_id == RawMessage.id)
        .join(ParseResultRow, ParseResultRow.message_version_id == RawMessageVersion.id)
        .where(
            RawMessage.author_tg_id == telegram_user_id,
            RawMessageVersion.version == RawMessage.latest_version,
            ParseResultRow.is_latest,
            ParseResultRow.employee_unresolved,
            ParseResultRow.resolution == Resolution.PENDING,
        )
        .order_by(RawMessage.sent_at)
    )
    outcomes = [
        await interpret(session, raw, ver, settings, actor=actor) for raw, ver in rows.all()
    ]
    return ReprocessReport(len(outcomes), outcomes)


async def link_identity(
    session: AsyncSession,
    identity_id: int,
    employee_id: int | None,
    settings: AppSettings,
    *,
    actor: str,
) -> ReprocessReport:
    identity = await session.get(TelegramIdentity, identity_id)
    if identity is None:
        raise EditError("Аккаунт не найден")
    if employee_id is not None and await session.get(Employee, employee_id) is None:
        raise EditError("Сотрудник не найден")
    before = {"employee_id": identity.employee_id}
    identity.employee_id = employee_id
    identity.linked_at = clock.now() if employee_id else None
    if employee_id:
        identity.suggested_employee_id = None
    await session.flush()
    await audit.record(
        session, actor=actor, action="identity.link", entity_type="telegram_identity",
        entity_id=identity.id, employee_id=employee_id, before=before,
        after={"employee_id": employee_id, "telegram_user_id": identity.telegram_user_id},
    )  # fmt: skip
    report = ReprocessReport(0, [])
    if employee_id:
        report = await reprocess_author(session, identity.telegram_user_id, settings, actor=actor)
    await events.notify(session, "identity.changed", employee_id=employee_id)
    return report


async def resolve_parse(
    session: AsyncSession, parse_id: int, resolution: Resolution, *, actor: str, reason: str = ""
) -> ParseResultRow:
    row = await session.get(
        ParseResultRow, parse_id, options=[selectinload(ParseResultRow.version)]
    )
    if row is None:
        raise EditError("Запись инбокса не найдена")
    if resolution is Resolution.IGNORED:
        raw = await session.get(RawMessage, row.version.raw_message_id)
        assert raw is not None
        await retract_derived(session, raw)
    before = {"resolution": row.resolution.value}
    row.resolution = resolution
    row.resolved_at = clock.now()
    await audit.record(
        session, actor=actor, action=f"inbox.{resolution.value}", entity_type="parse_result",
        entity_id=row.id, employee_id=row.employee_id, before=before,
        after={"resolution": resolution.value}, reason=reason,
    )  # fmt: skip
    await events.notify(session, "inbox.changed", parse_result_id=row.id)
    return row


async def reparse(
    session: AsyncSession, parse_id: int, settings: AppSettings, *, actor: str
) -> IngestOutcome:
    row = await session.get(
        ParseResultRow, parse_id, options=[selectinload(ParseResultRow.version)]
    )
    if row is None:
        raise EditError("Запись не найдена")
    raw = await session.get(RawMessage, row.version.raw_message_id)
    assert raw is not None
    latest = await session.scalar(
        select(RawMessageVersion).where(
            RawMessageVersion.raw_message_id == raw.id,
            RawMessageVersion.version == raw.latest_version,
        )
    )
    assert latest is not None
    return await interpret(session, raw, latest, settings, actor=actor)
