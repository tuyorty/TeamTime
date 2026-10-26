"""Приём сообщения: сохранить исходник, разобрать, сопоставить сотрудника, создать версии.

Одна точка входа для бота, импорта истории и демо-эмулятора. Идемпотентно по
``(chat_id, message_id)``: повтор того же текста ничего не меняет, новый текст — это правка.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from teamtime.core import clock
from teamtime.core.logging import get_logger
from teamtime.db.models import (
    BotChat,
    Daily,
    DailyInterval,
    DailyTask,
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
    TopicBinding,
    TopicKind,
)
from teamtime.parsing import (
    PARSER_VERSION,
    Issue,
    MessageKind,
    ParseResult,
    ParseStatus,
    Severity,
    detect_kind,
    parse_message,
)
from teamtime.services import events
from teamtime.services.matching import (
    candidates_by_surname,
    employee_by_person,
    upsert_identity,
)
from teamtime.services.serialize import issue_to_json, result_to_json
from teamtime.services.settings import AppSettings, load_settings

log = get_logger(__name__)

TOPIC_TO_KIND = {TopicKind.SCHEDULE: MessageKind.SCHEDULE, TopicKind.DAILY: MessageKind.DAILY}


@dataclass(frozen=True, slots=True)
class IncomingMessage:
    chat_id: int
    message_id: int
    text: str
    sent_at: datetime
    thread_id: int | None = None
    author_id: int | None = None
    author_name: str = ""
    author_username: str | None = None
    edited_at: datetime | None = None
    source: Source = Source.TELEGRAM
    chat_title: str = ""
    is_forum: bool = False


@dataclass(slots=True)
class IngestOutcome:
    skipped: str | None = None
    """Причина, по которой сообщение не сохранено (не наша тема и не похоже на шаблон)."""
    kind: MessageKind = MessageKind.UNKNOWN
    status: ParseStatus | None = None
    raw_message_id: int | None = None
    parse_result_id: int | None = None
    employee_id: int | None = None
    employee_name: str | None = None
    employee_unresolved: bool = False
    is_edit: bool = False
    changed: bool = True
    issues: list[Issue] = field(default_factory=list)
    candidates: list[str] = field(default_factory=list)
    dates: list[date] = field(default_factory=list)

    @property
    def needs_attention(self) -> bool:
        return self.kind is not MessageKind.UNKNOWN and (
            self.status is not ParseStatus.OK or self.employee_unresolved
        )

    @property
    def problems(self) -> list[Issue]:
        return [i for i in self.issues if i.severity is not Severity.INFO]


async def topic_binding(
    session: AsyncSession, chat_id: int, thread_id: int | None
) -> TopicBinding | None:
    return await session.scalar(
        select(TopicBinding).where(
            TopicBinding.chat_id == chat_id,
            TopicBinding.thread_id.is_(None)
            if thread_id is None
            else TopicBinding.thread_id == thread_id,
        )
    )


async def ingest(
    session: AsyncSession, msg: IncomingMessage, settings: AppSettings | None = None
) -> IngestOutcome:
    settings = settings or await load_settings(session)
    binding = await topic_binding(session, msg.chat_id, msg.thread_id)
    hint = TOPIC_TO_KIND.get(binding.kind) if binding else None

    raw = await session.scalar(
        select(RawMessage).where(
            RawMessage.chat_id == msg.chat_id, RawMessage.message_id == msg.message_id
        )
    )
    is_edit = False
    if raw is None:
        if binding is None and detect_kind(msg.text) is MessageKind.UNKNOWN:
            return IngestOutcome(skipped="not_relevant")
        await _ensure_chat(session, msg)
        raw = RawMessage(
            chat_id=msg.chat_id,
            message_id=msg.message_id,
            thread_id=msg.thread_id,
            author_tg_id=msg.author_id,
            author_name=msg.author_name,
            sent_at=msg.sent_at,
            source=msg.source,
            latest_version=1,
        )
        session.add(raw)
        await session.flush()
        version = RawMessageVersion(raw_message_id=raw.id, version=1, text=msg.text, edited_at=None)
        session.add(version)
    else:
        latest = await session.scalar(
            select(RawMessageVersion).where(
                RawMessageVersion.raw_message_id == raw.id,
                RawMessageVersion.version == raw.latest_version,
            )
        )
        if latest is not None and latest.text == msg.text:
            return await _replay_outcome(session, raw)
        is_edit = True
        raw.latest_version += 1
        version = RawMessageVersion(
            raw_message_id=raw.id,
            version=raw.latest_version,
            text=msg.text,
            edited_at=msg.edited_at or clock.now(),
        )
        session.add(version)
    await session.flush()

    identity = None
    if msg.author_id is not None:
        identity = await upsert_identity(
            session, msg.author_id, msg.author_name, msg.author_username, msg.sent_at
        )
    outcome = await interpret(session, raw, version, settings, identity=identity, hint=hint)
    outcome.is_edit = is_edit
    log.info(
        "message.ingested",
        chat_id=msg.chat_id,
        message_id=msg.message_id,
        kind=outcome.kind.value,
        status=outcome.status.value if outcome.status else None,
        employee_id=outcome.employee_id,
        edit=is_edit,
    )
    return outcome


async def _ensure_chat(session: AsyncSession, msg: IncomingMessage) -> None:
    chat = await session.get(BotChat, msg.chat_id)
    if chat is None:
        session.add(BotChat(chat_id=msg.chat_id, title=msg.chat_title, is_forum=msg.is_forum))
    elif msg.chat_title and chat.title != msg.chat_title:
        chat.title = msg.chat_title


async def _replay_outcome(session: AsyncSession, raw: RawMessage) -> IngestOutcome:
    """Повтор того же сообщения (ретрай, повторный импорт): вернуть прошлый итог без изменений."""
    row = await session.scalar(
        select(ParseResultRow)
        .join(RawMessageVersion, ParseResultRow.message_version_id == RawMessageVersion.id)
        .where(RawMessageVersion.raw_message_id == raw.id, ParseResultRow.is_latest)
    )
    if row is None:
        return IngestOutcome(raw_message_id=raw.id, changed=False)
    employee = await session.get(Employee, row.employee_id) if row.employee_id else None
    return IngestOutcome(
        kind=row.kind,
        status=row.status,
        raw_message_id=raw.id,
        parse_result_id=row.id,
        employee_id=row.employee_id,
        employee_name=employee.short_name if employee else None,
        employee_unresolved=row.employee_unresolved,
        changed=False,
        issues=[
            Issue(i["code"], Severity(i["severity"]), i["message"], i.get("line_no"), i.get("line"))
            for i in row.issues
        ],
    )


async def interpret(
    session: AsyncSession,
    raw: RawMessage,
    version: RawMessageVersion,
    settings: AppSettings,
    *,
    identity: TelegramIdentity | None = None,
    hint: MessageKind | None = None,
    actor: str = "bot",
) -> IngestOutcome:
    """Разобрать версию сообщения и пересоздать производные версии плана или дейлика.

    Вызывается при приёме, правке и переразборе (например, после привязки аккаунта).
    """
    if identity is None and raw.author_tg_id is not None:
        identity = await session.scalar(
            select(TelegramIdentity).where(TelegramIdentity.telegram_user_id == raw.author_tg_id)
        )
    if hint is None:
        binding = await topic_binding(session, raw.chat_id, raw.thread_id)
        hint = TOPIC_TO_KIND.get(binding.kind) if binding else None

    result = parse_message(version.text, raw.sent_at, settings.tz, topic_hint=hint)
    dates = await retract_derived(session, raw)
    await session.execute(
        update(ParseResultRow)
        .where(
            ParseResultRow.message_version_id.in_(
                select(RawMessageVersion.id).where(RawMessageVersion.raw_message_id == raw.id)
            )
        )
        .values(is_latest=False)
    )

    outcome = IngestOutcome(kind=result.kind, raw_message_id=raw.id, issues=list(result.issues))
    if result.kind is MessageKind.UNKNOWN:
        row = _parse_row(version, result, None, unresolved=False, resolution=Resolution.IGNORED)
        session.add(row)
        await session.flush()
        outcome.parse_result_id = row.id
        outcome.status = result.status
        return outcome

    employee, extra, candidates = await _resolve_employee(session, result, identity)
    outcome.issues.extend(extra)
    outcome.candidates = [c.short_name for c in candidates]
    unresolved = employee is None
    status = _status(
        outcome.issues, has_data=result.schedule is not None or result.daily is not None
    )
    resolution = (
        Resolution.AUTO if status is ParseStatus.OK and not unresolved else Resolution.PENDING
    )
    row = _parse_row(
        version,
        result,
        employee,
        unresolved=unresolved,
        resolution=resolution,
        issues=outcome.issues,
        status=status,
    )
    session.add(row)
    await session.flush()
    outcome.parse_result_id = row.id
    outcome.status = status
    outcome.employee_unresolved = unresolved
    if employee is not None:
        outcome.employee_id = employee.id
        outcome.employee_name = employee.short_name

    if employee is not None and status is not ParseStatus.FAILED:
        is_edit = version.version > 1
        if result.schedule is not None:
            plan = await create_plan_version(
                session, employee.id, result, version, row.id, raw.source, actor, edited=is_edit
            )
            dates.extend(d.date for d in plan.days)
        elif result.daily is not None:
            daily = await create_daily_version(
                session, employee.id, result, version, row.id, raw.source, actor,
                edited=is_edit, sent_at=raw.sent_at,
            )  # fmt: skip
            dates.append(daily.work_date)

    outcome.dates = sorted(set(dates))
    await events.notify(
        session,
        "message.ingested",
        kind=result.kind.value,
        status=status.value,
        employee_id=outcome.employee_id,
        employee=outcome.employee_name,
        dates=[d.isoformat() for d in outcome.dates],
        edited=version.version > 1,
        parse_result_id=row.id,
    )
    return outcome


def _status(issues: list[Issue], *, has_data: bool) -> ParseStatus:
    severities = {i.severity for i in issues}
    if not has_data or Severity.ERROR in severities:
        return ParseStatus.FAILED
    if Severity.WARNING in severities:
        return ParseStatus.PARTIAL
    return ParseStatus.OK


def _parse_row(
    version: RawMessageVersion,
    result: ParseResult,
    employee: Employee | None,
    *,
    unresolved: bool,
    resolution: Resolution,
    issues: list[Issue] | None = None,
    status: ParseStatus | None = None,
) -> ParseResultRow:
    return ParseResultRow(
        message_version_id=version.id,
        parser_version=PARSER_VERSION,
        kind=result.kind,
        status=status or result.status,
        issues=[issue_to_json(i) for i in (issues if issues is not None else result.issues)],
        data=result_to_json(result),
        employee_id=employee.id if employee else None,
        employee_unresolved=unresolved,
        resolution=resolution,
        is_latest=True,
    )


async def _resolve_employee(
    session: AsyncSession, result: ParseResult, identity: TelegramIdentity | None
) -> tuple[Employee | None, list[Issue], list[Employee]]:
    issues: list[Issue] = []
    linked = (
        await session.get(Employee, identity.employee_id)
        if identity and identity.employee_id
        else None
    )

    if result.schedule is not None and result.schedule.person is not None:
        person = result.schedule.person
        employee = await employee_by_person(session, person)
        if employee is not None:
            if identity is not None and identity.employee_id is None:
                identity.suggested_employee_id = employee.id
            elif linked is not None and linked.id != employee.id:
                issues.append(
                    Issue("posted_for_other", Severity.INFO,
                          f"Расписание {employee.short_name} прислал {linked.short_name}")
                )  # fmt: skip
            return employee, issues, []
        candidates = await candidates_by_surname(session, person.surname)
        if linked is not None:
            issues.append(
                Issue("person_not_found_used_sender", Severity.WARNING,
                      f"Сотрудник «{person.raw}» не найден, взят привязанный аккаунт "
                      f"{linked.short_name}")
            )  # fmt: skip
            return linked, issues, candidates
        hint = f": возможно, {', '.join(c.short_name for c in candidates)}" if candidates else ""
        issues.append(
            Issue("employee_not_found", Severity.WARNING,
                  f"Сотрудник «{person.raw}» не найден в справочнике{hint}")
        )  # fmt: skip
        return None, issues, candidates

    if linked is not None:
        return linked, issues, []
    suggestion = (
        await session.get(Employee, identity.suggested_employee_id)
        if identity and identity.suggested_employee_id
        else None
    )
    who = f"«{identity.display_name}»" if identity else "отправителя"
    hint = f" Похоже на {suggestion.short_name}." if suggestion else ""
    issues.append(
        Issue("identity_not_linked", Severity.WARNING,
              f"Аккаунт {who} не привязан к сотруднику.{hint}")
    )  # fmt: skip
    return None, issues, [suggestion] if suggestion else []


async def retract_derived(session: AsyncSession, raw: RawMessage) -> list[date]:
    """Отозвать версии планов и дейликов, полученные из прошлых версий этого сообщения."""
    now = clock.now()
    version_ids = select(RawMessageVersion.id).where(RawMessageVersion.raw_message_id == raw.id)
    dates: list[date] = []
    plans = await session.scalars(
        select(SchedulePlan).where(
            SchedulePlan.source_version_id.in_(version_ids), SchedulePlan.retracted_at.is_(None)
        )
    )
    for plan in plans:
        plan.retracted_at = now
        dates.extend(d.date for d in await plan.awaitable_attrs.days)
    dailies = await session.scalars(
        select(Daily).where(Daily.source_version_id.in_(version_ids), Daily.retracted_at.is_(None))
    )
    for daily in dailies:
        daily.retracted_at = now
        dates.append(daily.work_date)
    return dates


async def next_version(session: AsyncSession, model: type[Any], *where: Any) -> int:
    current = await session.scalar(select(func.max(model.version)).where(*where))
    return (current or 0) + 1


async def create_plan_version(
    session: AsyncSession,
    employee_id: int,
    result: ParseResult,
    version: RawMessageVersion | None,
    parse_result_id: int | None,
    source: Source,
    actor: str,
    *,
    edited: bool = False,
) -> SchedulePlan:
    s = result.schedule
    assert s is not None
    plan = SchedulePlan(
        employee_id=employee_id,
        iso_year=s.iso_year,
        iso_week=s.iso_week,
        week_start=s.week_start,
        sprint_start=s.sprint_start,
        sprint_end=s.sprint_end,
        version=await next_version(
            session,
            SchedulePlan,
            SchedulePlan.employee_id == employee_id,
            SchedulePlan.iso_year == s.iso_year,
            SchedulePlan.iso_week == s.iso_week,
        ),
        source=source,
        source_version_id=version.id if version else None,
        parse_result_id=parse_result_id,
        created_by=actor,
        edited=edited,
        days=[
            PlanDay(
                date=d.date,
                kind=d.kind,
                start_sec=d.start,
                end_sec=d.end,
                planned_sec=d.planned_seconds,
                intervals=[[i.start, i.end] for i in d.intervals],
                note=d.note,
                note_has_time=d.note_has_time,
                raw_line=d.raw_line,
            )
            for d in s.days
        ],
        tasks=[SprintTask(position=n, text=t) for n, t in enumerate(s.tasks)],
    )
    session.add(plan)
    await session.flush()
    return plan


async def create_daily_version(
    session: AsyncSession,
    employee_id: int,
    result: ParseResult,
    version: RawMessageVersion | None,
    parse_result_id: int | None,
    source: Source,
    actor: str,
    *,
    edited: bool = False,
    sent_at: datetime | None = None,
) -> Daily:
    d = result.daily
    assert d is not None
    daily = Daily(
        employee_id=employee_id,
        work_date=d.work_date,
        version=await next_version(
            session, Daily, Daily.employee_id == employee_id, Daily.work_date == d.work_date
        ),
        efficiency=d.efficiency,
        source=source,
        source_version_id=version.id if version else None,
        parse_result_id=parse_result_id,
        created_by=actor,
        edited=edited,
        sent_at=sent_at,
        intervals=[
            DailyInterval(position=n, start_sec=i.start, end_sec=i.end)
            for n, i in enumerate(d.intervals)
        ],
        tasks=[DailyTask(position=n, text=t) for n, t in enumerate(d.tasks)],
    )
    session.add(daily)
    await session.flush()
    return daily
