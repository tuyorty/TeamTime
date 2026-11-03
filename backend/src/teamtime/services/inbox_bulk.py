"""Массовое решение старых вопросов без подстановки эффективности и рабочих часов."""

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from teamtime.core import clock
from teamtime.db.models import ParseResultRow, RawMessage, RawMessageVersion, Resolution, Source
from teamtime.parsing import MessageKind, ParseStatus
from teamtime.services import audit, events
from teamtime.services.settings import AppSettings

Target = Literal["missing_efficiency", "no_time"]


class BulkFilter(BaseModel):
    target: Target
    employee_id: int | None = None
    chat_id: int | None = None
    start: date | None = None
    end: date | None = None
    import_only: bool = True

    @model_validator(mode="after")
    def dates(self) -> "BulkFilter":
        if self.start and self.end and self.end < self.start:
            raise ValueError("Конец периода раньше начала")
        return self


class BulkApply(BaseModel):
    target: Target
    parse_ids: list[int] = Field(min_length=1, max_length=5000)


def eligible(row: ParseResultRow, target: Target) -> bool:
    if (
        not row.is_latest
        or row.resolution is not Resolution.PENDING
        or row.kind is not MessageKind.DAILY
    ):
        return False
    if target == "no_time":
        return (
            row.status is ParseStatus.FAILED
            and not row.data
            and any(issue["code"] == "no_intervals" for issue in row.issues)
        )
    return bool(
        row.status is ParseStatus.PARTIAL
        and not row.employee_unresolved
        and row.data
        and row.data.get("efficiency") is None
        and row.data.get("intervals")
        and any(issue["code"] == "no_efficiency" for issue in row.issues)
        and all(
            issue["severity"] == "info" or issue["code"] == "no_efficiency" for issue in row.issues
        )
    )


async def preview(
    session: AsyncSession, settings: AppSettings, filters: BulkFilter
) -> dict[str, Any]:
    query = (
        select(ParseResultRow, RawMessage, RawMessageVersion)
        .join(RawMessageVersion, ParseResultRow.message_version_id == RawMessageVersion.id)
        .join(RawMessage, RawMessageVersion.raw_message_id == RawMessage.id)
        .where(
            ParseResultRow.is_latest,
            ParseResultRow.resolution == Resolution.PENDING,
            ParseResultRow.kind == MessageKind.DAILY,
        )
        .order_by(RawMessage.sent_at, ParseResultRow.id)
    )
    if filters.employee_id is not None:
        query = query.where(ParseResultRow.employee_id == filters.employee_id)
    if filters.chat_id is not None:
        query = query.where(RawMessage.chat_id == filters.chat_id)
    if filters.import_only:
        query = query.where(RawMessage.source == Source.IMPORT)
    local_day = func.date(
        func.timezone(
            settings.timezone, func.coalesce(RawMessageVersion.edited_at, RawMessage.sent_at)
        )
    )
    if filters.start:
        query = query.where(local_day >= filters.start)
    if filters.end:
        query = query.where(local_day <= filters.end)
    matches = [
        (row, raw, version)
        for row, raw, version in (await session.execute(query)).all()
        if eligible(row, filters.target)
    ]
    if len(matches) > 5000:
        raise ValueError("Найдено больше 5000 записей. Уточните сотрудника или период.")
    return {
        "parse_ids": [row.id for row, _, _ in matches],
        "count": len(matches),
        "samples": [
            {
                "id": row.id,
                "author": raw.author_name,
                "sent_at": raw.sent_at.isoformat(),
                "text": version.text[:500],
            }
            for row, raw, version in matches[:8]
        ],
    }


async def apply(session: AsyncSession, body: BulkApply, actor: str) -> int:
    ids = sorted(set(body.parse_ids))
    rows = list(
        await session.scalars(
            select(ParseResultRow).where(ParseResultRow.id.in_(ids)).with_for_update()
        )
    )
    if len(rows) != len(ids) or any(not eligible(row, body.target) for row in rows):
        raise ValueError("Записи изменились после предпросмотра. Обновите выборку.")
    resolution = Resolution.ACCEPTED if body.target == "missing_efficiency" else Resolution.IGNORED
    await session.execute(
        update(ParseResultRow)
        .where(ParseResultRow.id.in_(ids))
        .values(resolution=resolution, resolved_at=clock.now())
    )
    await audit.record(
        session,
        actor=actor,
        action="inbox.bulk_resolve",
        entity_type="inbox",
        entity_id=0,
        after={
            "target": body.target,
            "resolution": resolution.value,
            "parse_ids": ids,
            "count": len(ids),
            "hours_changed": False,
        },
        reason="Старые дейлики: эффективность неизвестна"
        if body.target == "missing_efficiency"
        else "Старые сообщения без времени: закрыто без начисления часов",
    )
    await events.notify(session, "inbox.changed")
    return len(ids)
