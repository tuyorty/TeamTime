"""Отдел сотрудника задаётся явно либо по назначенному администратором отделу чата."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from teamtime.db.models import BotChat, Employee, ParseResultRow, RawMessage, RawMessageVersion
from teamtime.services import audit, events


async def assign_from_chat(
    session: AsyncSession, employee: Employee, chat_id: int, parse_id: int
) -> None:
    department = await session.scalar(select(BotChat.department).where(BotChat.chat_id == chat_id))
    if department and employee.department != department:
        # Не меняем отдел при каждом сообщении сотрудника в другой беседе.
        # Для переноса существующей команды есть явное действие администратора.
        has_other = await session.scalar(
            select(ParseResultRow.id)
            .join(RawMessageVersion, ParseResultRow.message_version_id == RawMessageVersion.id)
            .join(RawMessage, RawMessageVersion.raw_message_id == RawMessage.id)
            .where(ParseResultRow.employee_id == employee.id, ParseResultRow.id != parse_id)
            .limit(1)
        )
        if has_other is None:
            employee.department = department
            await events.notify(session, "employee.changed", employee_id=employee.id)


async def set_chat_department(
    session: AsyncSession, chat: BotChat, department: str | None, *, actor: str
) -> int:
    before = chat.department
    chat.department = department
    ids = (
        list(
            await session.scalars(
                select(ParseResultRow.employee_id)
                .join(RawMessageVersion, ParseResultRow.message_version_id == RawMessageVersion.id)
                .join(RawMessage, RawMessageVersion.raw_message_id == RawMessage.id)
                .where(
                    RawMessage.chat_id == chat.chat_id,
                    ParseResultRow.is_latest,
                    ParseResultRow.employee_id.is_not(None),
                )
                .distinct()
            )
        )
        if department
        else []
    )
    employees = list(await session.scalars(select(Employee).where(Employee.id.in_(ids))))
    changes = []
    for employee in employees:
        if department is not None and employee.department != department:
            changes.append({"employee_id": employee.id, "before": employee.department})
            employee.department = department
    await audit.record(
        session,
        actor=actor,
        action="chat.department",
        entity_type="bot_chat",
        entity_id=chat.chat_id,
        before={"department": before},
        after={"department": department, "employees": changes},
    )
    await events.notify(session, "employee.changed")
    return len(changes)
