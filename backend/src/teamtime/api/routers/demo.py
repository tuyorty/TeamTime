"""Демо-эмулятор чата: сообщение «как из Telegram» без Telegram. Только при DEMO=1."""

from __future__ import annotations

from datetime import date
from typing import Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from teamtime.api.deps import AdminDep, AppSettingsDep, SessionDep
from teamtime.calc import StatusKind
from teamtime.core import clock
from teamtime.db.models import Employee, RawMessage, Source, TelegramIdentity
from teamtime.demo.constants import (
    DAILY_THREAD_ID,
    DEMO_CHAT_ID,
    DEMO_CHAT_TITLE,
    SCHEDULE_THREAD_ID,
)
from teamtime.demo.forum import ensure_demo_forum
from teamtime.schemas import IssueOut
from teamtime.services import manual, status_requests
from teamtime.services.ingest import IncomingMessage, ingest

router = APIRouter(prefix="/demo", tags=["демо"])


class DemoStatusIn(BaseModel):
    employee_id: int
    start: date
    end: date
    kind: StatusKind | None = StatusKind.REMOTE
    note: str = Field("Пример заявки из эмулятора", max_length=500)


class DemoStatusOut(BaseModel):
    request_id: int


@router.post("/status-requests", summary="Создать в демо заявку, аналогичную /absent")
async def request_demo_status(
    body: DemoStatusIn, session: SessionDep, actor: AdminDep
) -> DemoStatusOut:
    employee = await session.get(Employee, body.employee_id)
    if employee is None:
        raise HTTPException(404, "Сотрудник не найден")
    try:
        row = await status_requests.request_status(
            session, employee, body.start, body.end, body.kind, f"demo:{actor}", body.note
        )
    except manual.EditError as exc:
        raise HTTPException(422, str(exc)) from exc
    return DemoStatusOut(request_id=row.id)


class DemoMessageIn(BaseModel):
    telegram_user_id: int
    topic: Literal["schedule", "daily"]
    text: str = Field(min_length=1, max_length=4000)
    edit_raw_message_id: int | None = Field(None, description="Отредактировать прошлое сообщение")


class DemoMessageOut(BaseModel):
    raw_message_id: int | None
    reaction: str | None
    reply: str | None
    status: str | None
    kind: str
    employee: str | None
    issues: list[IssueOut]


@router.post("/messages", summary="Отправить сообщение в эмулятор чата")
async def send(
    body: DemoMessageIn, session: SessionDep, settings: AppSettingsDep
) -> DemoMessageOut:
    identity = await session.scalar(
        select(TelegramIdentity).where(TelegramIdentity.telegram_user_id == body.telegram_user_id)
    )
    if identity is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Нет такого участника демо-чата")
    await ensure_demo_forum(session)
    if body.edit_raw_message_id is not None:
        raw = await session.get(RawMessage, body.edit_raw_message_id)
        if raw is None or raw.chat_id != DEMO_CHAT_ID:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Сообщение не найдено")
        message_id, thread_id, sent_at = raw.message_id, raw.thread_id, raw.sent_at
    else:
        last = await session.scalar(
            select(func.max(RawMessage.message_id)).where(RawMessage.chat_id == DEMO_CHAT_ID)
        )
        message_id = (last or 0) + 1
        thread_id = SCHEDULE_THREAD_ID if body.topic == "schedule" else DAILY_THREAD_ID
        sent_at = clock.now()
    outcome = await ingest(
        session,
        IncomingMessage(
            chat_id=DEMO_CHAT_ID,
            message_id=message_id,
            thread_id=thread_id,
            text=body.text,
            sent_at=sent_at,
            edited_at=clock.now() if body.edit_raw_message_id else None,
            author_id=identity.telegram_user_id,
            author_name=identity.display_name,
            author_username=identity.username,
            source=Source.DEMO,
            chat_title=DEMO_CHAT_TITLE,
            is_forum=True,
        ),
        settings,
    )
    # Эмулятор показывает ровно то, что бот сделал бы в теме.
    from teamtime.bot.feedback import group_feedback

    fb = group_feedback(outcome, settings, bot_username="teamtime_demo_bot")
    return DemoMessageOut(
        raw_message_id=outcome.raw_message_id,
        reaction=fb.reaction,
        reply=fb.reply,
        status=outcome.status.value if outcome.status else None,
        kind=outcome.kind.value,
        employee=outcome.employee_name,
        issues=[IssueOut(**{
            "code": i.code, "severity": i.severity.value, "message": i.message,
            "line_no": i.line_no, "line": i.line,
        }) for i in outcome.issues],
    )  # fmt: skip
