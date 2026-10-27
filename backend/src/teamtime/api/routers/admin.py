"""Правки и настройки: только в режиме админа. Каждая правка пишется в аудит."""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Form, HTTPException, Path, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select

from teamtime.api.deps import AdminDep, AdminReadDep, AppSettingsDep, SessionDep
from teamtime.calc import StatusKind
from teamtime.db.models import BotChat, Employee, Resolution, TopicBinding
from teamtime.parsing import PlanDayKind
from teamtime.schemas import ChatIn, ChatOut, EmployeeIn, EmployeeOut, TopicIn, TopicOut
from teamtime.services import audit, events, manual
from teamtime.services.settings import AppSettings, save_settings

router = APIRouter(prefix="/admin", tags=["админка"])


def _bad(exc: manual.EditError) -> HTTPException:
    return HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc))


class OkOut(BaseModel):
    ok: bool = True
    detail: str = ""


# --- сотрудники ----------------------------------------------------------------------------


@router.post("/employees", summary="Добавить сотрудника", status_code=status.HTTP_201_CREATED)
async def create_employee(body: EmployeeIn, session: SessionDep, actor: AdminDep) -> EmployeeOut:
    try:
        e = await manual.save_employee(session, body.model_dump(), actor=actor)
    except manual.EditError as exc:
        raise _bad(exc) from exc
    return EmployeeOut.model_validate(e)


@router.put("/employees/{employee_id}", summary="Изменить сотрудника")
async def update_employee(
    employee_id: int, body: EmployeeIn, session: SessionDep, actor: AdminDep
) -> EmployeeOut:
    e = await session.get(Employee, employee_id)
    if e is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Сотрудник не найден")
    try:
        e = await manual.save_employee(session, body.model_dump(), actor=actor, employee=e)
    except manual.EditError as exc:
        raise _bad(exc) from exc
    return EmployeeOut.model_validate(e)


@router.delete("/employees/{employee_id}", summary="Удалить сотрудника с его планами и дейликами")
async def delete_employee(employee_id: int, session: SessionDep, actor: AdminDep) -> OkOut:
    e = await session.get(Employee, employee_id)
    if e is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Сотрудник не найден")
    report = await manual.delete_employee(session, e, actor=actor)
    return OkOut(detail=f"Удалено: дейликов {report.dailies}, версий планов {report.plans}")


# --- аккаунты Telegram ---------------------------------------------------------------------


class LinkIn(BaseModel):
    employee_id: int | None


class LinkOut(OkOut):
    reprocessed: int = 0


@router.put("/identities/{identity_id}", summary="Привязать аккаунт Telegram к сотруднику")
async def link_identity(
    identity_id: int, body: LinkIn, session: SessionDep, settings: AppSettingsDep, actor: AdminDep
) -> LinkOut:
    try:
        report = await manual.link_identity(
            session, identity_id, body.employee_id, settings, actor=actor
        )
    except manual.EditError as exc:
        raise _bad(exc) from exc
    detail = f"Переразобрано сообщений: {report.reprocessed}" if report.reprocessed else ""
    return LinkOut(reprocessed=report.reprocessed, detail=detail)


# --- чаты ---------------------------------------------------------------------------------


@router.get("/chats", summary="Чаты, в которые добавлен бот")
async def chats(session: SessionDep, _: AdminReadDep) -> list[ChatOut]:
    counts = (
        select(TopicBinding.chat_id, func.count().label("n"))
        .group_by(TopicBinding.chat_id)
        .subquery()
    )
    rows = await session.execute(
        select(BotChat, func.coalesce(counts.c.n, 0))
        .outerjoin(counts, counts.c.chat_id == BotChat.chat_id)
        .order_by(BotChat.approved.desc(), BotChat.added_at)
    )
    return [
        ChatOut(
            chat_id=c.chat_id, title=c.title, is_forum=c.is_forum, approved=c.approved, topics=n
        )
        for c, n in rows
    ]


@router.put("/chats/{chat_id}", summary="Разрешить или запретить чат")
async def set_chat(chat_id: int, body: ChatIn, session: SessionDep, actor: AdminDep) -> OkOut:
    chat = await session.get(BotChat, chat_id)
    if chat is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Чат не найден")
    before = chat.approved
    chat.approved = body.approved
    await audit.record(
        session, actor=actor, action="chat.approve" if body.approved else "chat.revoke",
        entity_type="bot_chat", entity_id=chat_id, before={"approved": before},
        after={"approved": body.approved, "title": chat.title},
    )  # fmt: skip
    await events.notify(session, "settings.changed")
    return OkOut(detail="Чат разрешён" if body.approved else "Чат запрещён")


@router.delete("/chats/{chat_id}", summary="Забыть чат и его привязки тем")
async def delete_chat(chat_id: int, session: SessionDep, actor: AdminDep) -> OkOut:
    chat = await session.get(BotChat, chat_id)
    if chat is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Чат не найден")
    await audit.record(
        session, actor=actor, action="chat.delete", entity_type="bot_chat", entity_id=chat_id,
        before={"title": chat.title, "approved": chat.approved},
    )  # fmt: skip
    session.expunge(chat)
    await session.execute(delete(BotChat).where(BotChat.chat_id == chat_id))  # темы — каскадом
    await events.notify(session, "settings.changed")
    return OkOut(detail="Чат удалён. Исходные сообщения из него остаются в базе")


# --- темы форума ---------------------------------------------------------------------------


@router.get("/topics", summary="Привязки тем форума")
async def topics(session: SessionDep, _: AdminReadDep) -> list[TopicOut]:
    rows = await session.execute(
        select(TopicBinding, BotChat.title).join(BotChat).order_by(TopicBinding.id)
    )
    return [
        TopicOut(
            id=t.id,
            chat_id=t.chat_id,
            thread_id=t.thread_id,
            kind=t.kind,
            title=t.title,
            chat_title=title,
        )
        for t, title in rows
    ]


@router.post(
    "/topics", summary="Привязать тему к типу сообщений", status_code=status.HTTP_201_CREATED
)
async def bind_topic(body: TopicIn, session: SessionDep, actor: AdminDep) -> TopicOut:
    chat = await session.get(BotChat, body.chat_id)
    if chat is None:
        chat = BotChat(chat_id=body.chat_id, title="", is_forum=body.thread_id is not None)
        session.add(chat)
    chat.approved = True  # тему привязывает сам админ — чат доверенный
    await session.flush()
    existing = await session.scalar(
        select(TopicBinding).where(
            TopicBinding.chat_id == body.chat_id,
            TopicBinding.thread_id.is_(None)
            if body.thread_id is None
            else TopicBinding.thread_id == body.thread_id,
        )
    )
    before = {"kind": existing.kind.value} if existing else None
    if existing is None:
        existing = TopicBinding(**body.model_dump())
        session.add(existing)
    else:
        existing.kind, existing.title = body.kind, body.title or existing.title
    await session.flush()
    await audit.record(
        session,
        actor=actor,
        action="topic.bind",
        entity_type="topic_binding",
        entity_id=existing.id,
        before=before,
        after=body.model_dump(mode="json"),
    )
    return TopicOut(
        id=existing.id, chat_id=existing.chat_id, thread_id=existing.thread_id, kind=existing.kind,
        title=existing.title,
    )  # fmt: skip


@router.delete("/topics/{topic_id}", summary="Отвязать тему")
async def unbind_topic(topic_id: int, session: SessionDep, actor: AdminDep) -> OkOut:
    t = await session.get(TopicBinding, topic_id)
    if t is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Привязка не найдена")
    await audit.record(
        session, actor=actor, action="topic.unbind", entity_type="topic_binding", entity_id=t.id,
        before={"chat_id": t.chat_id, "thread_id": t.thread_id, "kind": t.kind.value},
    )  # fmt: skip
    await session.delete(t)
    return OkOut()


# --- дни: факт, план, статус ---------------------------------------------------------------


class DailyIn(BaseModel):
    intervals: list[tuple[int, int]] | None = Field(
        None, description="Интервалы [начало, конец] в секундах от полуночи"
    )
    efficiency: int | None = Field(None, ge=0, le=100)
    keep_efficiency: bool = Field(False, description="Не менять эффективность")
    tasks: list[str] | None = None
    reason: str = ""
    parse_result_id: int | None = Field(
        None, description="Если правка из инбокса — пометить «исправлено»"
    )


DayPath = Annotated[date, Path(description="Дата ГГГГ-ММ-ДД")]


@router.put("/days/{employee_id}/{day}/fact", summary="Исправить факт дня (новая версия дейлика)")
async def set_fact(
    employee_id: int, day: DayPath, body: DailyIn, session: SessionDep, actor: AdminDep
) -> OkOut:
    try:
        await manual.set_daily(
            session,
            employee_id=employee_id,
            work_date=day,
            intervals=body.intervals,
            efficiency=manual.KEEP if body.keep_efficiency else body.efficiency,
            tasks=body.tasks,
            actor=actor,
            reason=body.reason,
            parse_result_id=body.parse_result_id,
        )
        if body.parse_result_id:
            await manual.resolve_parse(
                session, body.parse_result_id, Resolution.FIXED, actor=actor, reason=body.reason
            )
    except manual.EditError as exc:
        raise _bad(exc) from exc
    return OkOut()


@router.delete("/days/{employee_id}/{day}/fact", summary="Убрать факт дня (отозвать дейлик)")
async def clear_fact(
    employee_id: int, day: DayPath, session: SessionDep, actor: AdminDep, reason: str = ""
) -> OkOut:
    try:
        await manual.retract_daily(
            session, employee_id=employee_id, work_date=day, actor=actor, reason=reason
        )
    except manual.EditError as exc:
        raise _bad(exc) from exc
    return OkOut()


class PlanDayIn(BaseModel):
    kind: PlanDayKind | None = Field(description="None — убрать день из плана")
    intervals: list[tuple[int, int]] | None = None
    note: str | None = None
    reason: str = ""


@router.put("/days/{employee_id}/{day}/plan", summary="Исправить план дня (новая версия плана)")
async def set_plan(
    employee_id: int, day: DayPath, body: PlanDayIn, session: SessionDep, actor: AdminDep
) -> OkOut:
    try:
        await manual.set_plan_day(
            session, employee_id=employee_id, day=day, kind=body.kind, intervals=body.intervals,
            note=body.note, actor=actor, reason=body.reason,
        )  # fmt: skip
    except manual.EditError as exc:
        raise _bad(exc) from exc
    return OkOut()


class StatusIn(BaseModel):
    kind: StatusKind | None
    end: date | None = Field(None, description="Конец периода (включительно)")
    note: str = ""
    reason: str = ""


@router.put("/days/{employee_id}/{day}/status", summary="Поставить статус дня или периода")
async def set_status(
    employee_id: int, day: DayPath, body: StatusIn, session: SessionDep, actor: AdminDep
) -> OkOut:
    try:
        n = await manual.set_status_range(
            session, employee_id=employee_id, start=day, end=body.end or day, kind=body.kind,
            note=body.note, actor=actor, reason=body.reason,
        )  # fmt: skip
    except manual.EditError as exc:
        raise _bad(exc) from exc
    return OkOut(detail=f"Дней: {n}")


# --- инбокс --------------------------------------------------------------------------------


class ResolveIn(BaseModel):
    resolution: Resolution
    reason: str = ""


@router.post("/inbox/{parse_id}/resolve", summary="Принять или игнорировать запись инбокса")
async def resolve(parse_id: int, body: ResolveIn, session: SessionDep, actor: AdminDep) -> OkOut:
    if body.resolution not in {Resolution.ACCEPTED, Resolution.IGNORED, Resolution.PENDING}:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Можно: accepted, ignored, pending"
        )
    try:
        await manual.resolve_parse(
            session, parse_id, body.resolution, actor=actor, reason=body.reason
        )
    except manual.EditError as exc:
        raise _bad(exc) from exc
    return OkOut()


@router.post("/inbox/{parse_id}/reparse", summary="Переразобрать сообщение текущим парсером")
async def reparse(
    parse_id: int, session: SessionDep, settings: AppSettingsDep, actor: AdminDep
) -> OkOut:
    try:
        outcome = await manual.reparse(session, parse_id, settings, actor=actor)
    except manual.EditError as exc:
        raise _bad(exc) from exc
    return OkOut(detail=outcome.status.value if outcome.status else "")


# --- настройки -----------------------------------------------------------------------------


@router.get("/settings", summary="Бизнес-настройки")
async def get_settings_(settings: AppSettingsDep) -> AppSettings:
    return settings


class SettingsOut(BaseModel):
    settings: AppSettings
    warnings: list[str]


@router.put("/settings", summary="Сохранить бизнес-настройки")
async def put_settings(
    body: AppSettings, session: SessionDep, settings: AppSettingsDep, actor: AdminDep
) -> SettingsOut:
    await save_settings(session, body)
    await audit.record(
        session, actor=actor, action="settings.update", entity_type="settings", entity_id="app",
        before=settings.model_dump(mode="json"), after=body.model_dump(mode="json"),
    )  # fmt: skip
    await events.notify(session, "settings.changed")
    return SettingsOut(settings=body, warnings=body.penalty.scale().validate())


# --- импорт истории ------------------------------------------------------------------------


class ImportOut(BaseModel):
    chat_title: str
    chat_id: int
    total: int
    imported: int
    unchanged: int
    skipped: int
    older: int
    statuses: dict[str, int]
    topics: dict[str, str]
    errors: list[str]


MAX_IMPORT_BYTES = 50 * 1024 * 1024


@router.post("/import/telegram", summary="Импорт экспорта Telegram Desktop (result.json)")
async def import_telegram(
    file: UploadFile,
    session: SessionDep,
    settings: AppSettingsDep,
    actor: AdminDep,
    since: Annotated[date | None, Form(description="Только сообщения с этой даты")] = None,
) -> ImportOut:
    from teamtime.importer.telegram import ExportFormatError, import_export, load_export

    data = await file.read(MAX_IMPORT_BYTES + 1)
    if len(data) > MAX_IMPORT_BYTES:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "Файл больше 50 МБ: используйте CLI")
    try:
        report = await import_export(session, load_export(data), settings=settings, since=since)
    except ExportFormatError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from exc
    await audit.record(
        session,
        actor=actor,
        action="import.telegram",
        entity_type="import",
        entity_id=report.chat_id,
        after={k: v for k, v in report.as_dict().items() if k != "errors"},
        reason=file.filename or "",
    )
    await events.notify(session, "settings.changed")
    return ImportOut(**report.as_dict())
