"""Исходные сообщения и инбокс: показать источник, версии и разборы."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from teamtime.db.models import (
    Employee,
    ParseResultRow,
    RawMessage,
    RawMessageVersion,
    Resolution,
)
from teamtime.parsing import MessageKind, ParseStatus
from teamtime.schemas import (
    EmployeeBrief,
    InboxItem,
    InboxOut,
    IssueOut,
    MessageOut,
    MessageVersionOut,
    ParseResultOut,
)
from teamtime.services.matching import candidates_by_surname


def telegram_link(raw: RawMessage) -> str | None:
    """Ссылка t.me/c/… работает для участников приватной группы-форума."""
    if raw.chat_id >= 0 or raw.source.value not in {"telegram", "import"}:
        return None
    internal = str(raw.chat_id).removeprefix("-100")
    thread = f"/{raw.thread_id}" if raw.thread_id else ""
    return f"https://t.me/c/{internal}{thread}/{raw.message_id}"


def parse_out(row: ParseResultRow, version_no: int) -> ParseResultOut:
    return ParseResultOut(
        id=row.id,
        message_version_id=row.message_version_id,
        version=version_no,
        parser_version=row.parser_version,
        kind=row.kind,
        status=row.status,
        resolution=row.resolution,
        issues=[IssueOut(**i) for i in row.issues],
        data=row.data,
        employee=EmployeeBrief.model_validate(row.employee) if row.employee else None,
        employee_unresolved=row.employee_unresolved,
        created_at=row.created_at,
        is_latest=row.is_latest,
    )


async def message_out(session: AsyncSession, raw_id: int) -> MessageOut | None:
    raw = await session.get(RawMessage, raw_id, options=[selectinload(RawMessage.versions)])
    if raw is None:
        return None
    version_no = {v.id: v.version for v in raw.versions}
    parses = await session.scalars(
        select(ParseResultRow)
        .where(ParseResultRow.message_version_id.in_(version_no))
        .order_by(ParseResultRow.id)
        .options(selectinload(ParseResultRow.employee))
    )
    return MessageOut(
        id=raw.id,
        chat_id=raw.chat_id,
        message_id=raw.message_id,
        thread_id=raw.thread_id,
        author_name=raw.author_name,
        author_tg_id=raw.author_tg_id,
        sent_at=raw.sent_at,
        source=raw.source,
        versions=[MessageVersionOut.model_validate(v) for v in raw.versions],
        parses=[parse_out(p, version_no[p.message_version_id]) for p in parses],
        telegram_link=telegram_link(raw),
    )


INBOX_FILTERS = {
    "pending": [Resolution.PENDING],
    "resolved": [Resolution.ACCEPTED, Resolution.FIXED, Resolution.IGNORED],
    "auto": [Resolution.AUTO],
}


async def inbox(
    session: AsyncSession,
    view: str = "pending",
    limit: int = 100,
    *,
    employee: int | None = None,
    unlinked: bool = False,
    problem: str | None = None,
    kind: MessageKind | None = None,
) -> InboxOut:
    """Записи инбокса. Фильтры: сотрудник (или «не определён»), вид проблемы, тип сообщения."""
    resolutions = INBOX_FILTERS.get(view, INBOX_FILTERS["pending"])
    where = [
        ParseResultRow.is_latest,
        ParseResultRow.kind != MessageKind.UNKNOWN,
        ParseResultRow.resolution.in_(resolutions),
    ]
    if employee is not None:
        where.append(ParseResultRow.employee_id == employee)
    if unlinked or problem == "unlinked":
        where.append(ParseResultRow.employee_unresolved)
    if problem in {"failed", "partial"}:
        where.append(ParseResultRow.status == ParseStatus(problem))
    if kind is not None:
        where.append(ParseResultRow.kind == kind)
    total = await session.scalar(select(func.count()).select_from(ParseResultRow).where(*where))
    rows = await session.execute(
        select(ParseResultRow, RawMessageVersion)
        .join(RawMessageVersion, ParseResultRow.message_version_id == RawMessageVersion.id)
        .where(*where)
        .join(RawMessage, RawMessageVersion.raw_message_id == RawMessage.id)
        .order_by(func.coalesce(RawMessageVersion.edited_at, RawMessage.sent_at).desc())
        .limit(limit)
        .options(selectinload(ParseResultRow.employee))
    )
    items: list[InboxItem] = []
    for row, ver in rows.all():
        msg = await message_out(session, ver.raw_message_id)
        assert msg is not None
        candidates: list[Employee] = []
        person = (row.data or {}).get("person") if row.kind is MessageKind.SCHEDULE else None
        if row.employee_unresolved and person:
            candidates = await candidates_by_surname(session, person["surname"])
        items.append(
            InboxItem(
                parse=parse_out(row, ver.version),
                message=msg,
                candidates=[EmployeeBrief.model_validate(c) for c in candidates],
            )
        )

    counts_rows = await session.execute(
        select(ParseResultRow.resolution, ParseResultRow.status, func.count())
        .where(ParseResultRow.is_latest, ParseResultRow.kind != MessageKind.UNKNOWN)
        .group_by(ParseResultRow.resolution, ParseResultRow.status)
    )
    counts: dict[str, int] = {"pending": 0, "resolved": 0, "auto": 0, "failed": 0, "partial": 0}
    for resolution, status, n in counts_rows:
        for view_name, members in INBOX_FILTERS.items():
            if resolution in members:
                counts[view_name] += n
        if resolution is Resolution.PENDING and status is not ParseStatus.OK:
            counts[status.value] += n
    return InboxOut(items=items, counts=counts, total=total or 0)
