"""Отделы чатов, удаление неизвестных аккаунтов и пакетное решение инбокса."""

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from teamtime.api.deps import AdminDep, AdminReadDep, AppSettingsDep, SessionDep
from teamtime.core import clock
from teamtime.db.models import (
    BotChat,
    ParseResultRow,
    RawMessage,
    RawMessageVersion,
    Resolution,
    TelegramIdentity,
)
from teamtime.schemas import Department, IdentityOut
from teamtime.services import audit, departments, events, inbox_bulk, manual

router = APIRouter(prefix="/admin", tags=["админка"])


@router.delete("/identities/{identity_id}")
async def remove_identity(identity_id: int, session: SessionDep, actor: AdminDep) -> dict[str, Any]:
    identity = await session.scalar(
        select(TelegramIdentity).where(TelegramIdentity.id == identity_id).with_for_update()
    )
    if identity is None:
        raise HTTPException(404, "Аккаунт не найден")
    if identity.employee_id is not None:
        raise HTTPException(
            409, "Аккаунт привязан к сотруднику. Сначала проверьте и снимите привязку."
        )
    identity.removed_at = identity.removed_at or clock.now()
    ids = list(
        await session.scalars(
            select(ParseResultRow.id)
            .join(RawMessageVersion, ParseResultRow.message_version_id == RawMessageVersion.id)
            .join(RawMessage, RawMessageVersion.raw_message_id == RawMessage.id)
            .where(
                RawMessage.author_tg_id == identity.telegram_user_id,
                ParseResultRow.is_latest,
                ParseResultRow.employee_unresolved,
                ParseResultRow.resolution == Resolution.PENDING,
            )
        )
    )
    for parse_id in ids:
        await manual.resolve_parse(
            session,
            parse_id,
            Resolution.IGNORED,
            actor=actor,
            reason="Удалён неизвестный Telegram-аккаунт",
        )
    await audit.record(
        session,
        actor=actor,
        action="identity.remove",
        entity_type="telegram_identity",
        entity_id=identity.id,
        after={
            "telegram_user_id": identity.telegram_user_id,
            "display_name": identity.display_name,
            "closed": len(ids),
        },
    )
    await events.notify(session, "identity.changed")
    return {"detail": "Аккаунт удалён из списка. Исходные сообщения сохранены."}


@router.get("/identities/removed")
async def removed_identities(session: SessionDep, _: AdminReadDep) -> list[IdentityOut]:
    rows = await session.scalars(
        select(TelegramIdentity)
        .where(TelegramIdentity.removed_at.is_not(None))
        .options(
            selectinload(TelegramIdentity.employee),
            selectinload(TelegramIdentity.suggested_employee),
        )
    )
    return [IdentityOut.model_validate(row) for row in rows]


@router.post("/identities/{identity_id}/restore")
async def restore_identity(
    identity_id: int, session: SessionDep, actor: AdminDep
) -> dict[str, Any]:
    identity = await session.get(TelegramIdentity, identity_id)
    if identity is None:
        raise HTTPException(404, "Аккаунт не найден")
    identity.removed_at = None
    await audit.record(
        session,
        actor=actor,
        action="identity.restore",
        entity_type="telegram_identity",
        entity_id=identity.id,
        after={"telegram_user_id": identity.telegram_user_id},
    )
    await events.notify(session, "identity.changed")
    return {"detail": "Аккаунт восстановлен. Старые сообщения доступны в инбоксе «Решённые»."}


class ChatDepartmentIn(BaseModel):
    department: Department | None


@router.put("/chats/{chat_id}/department")
async def chat_department(
    chat_id: int, body: ChatDepartmentIn, session: SessionDep, actor: AdminDep
) -> dict[str, Any]:
    chat = await session.get(BotChat, chat_id)
    if chat is None:
        raise HTTPException(404, "Чат не найден")
    count = await departments.set_chat_department(session, chat, body.department, actor=actor)
    return {"detail": f"Отдел чата сохранён. Изменено сотрудников: {count}"}


@router.post("/inbox/bulk/preview")
async def bulk_preview(
    body: inbox_bulk.BulkFilter, session: SessionDep, settings: AppSettingsDep, _: AdminDep
) -> dict[str, Any]:
    try:
        return await inbox_bulk.preview(session, settings, body)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/inbox/bulk/apply")
async def bulk_apply(
    body: inbox_bulk.BulkApply, session: SessionDep, actor: AdminDep
) -> dict[str, Any]:
    try:
        count = await inbox_bulk.apply(session, body, actor)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    return {"detail": f"Закрыто записей: {count}. Часы и эффективность не изменены."}
