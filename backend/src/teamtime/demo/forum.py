"""Демо-чат-форум с двумя привязанными темами."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from teamtime.db.models import BotChat, TopicBinding, TopicKind
from teamtime.demo.constants import (
    DAILY_THREAD_ID,
    DEMO_CHAT_ID,
    DEMO_CHAT_TITLE,
    SCHEDULE_THREAD_ID,
)


async def ensure_demo_forum(session: AsyncSession) -> None:
    if await session.get(BotChat, DEMO_CHAT_ID) is None:
        session.add(BotChat(chat_id=DEMO_CHAT_ID, title=DEMO_CHAT_TITLE, is_forum=True))
        await session.flush()
    for thread, kind, title in (
        (SCHEDULE_THREAD_ID, TopicKind.SCHEDULE, "расписание"),
        (DAILY_THREAD_ID, TopicKind.DAILY, "дейлики"),
    ):
        exists = await session.scalar(
            select(TopicBinding.id).where(
                TopicBinding.chat_id == DEMO_CHAT_ID, TopicBinding.thread_id == thread
            )
        )
        if exists is None:
            session.add(
                TopicBinding(chat_id=DEMO_CHAT_ID, thread_id=thread, kind=kind, title=title)
            )
    await session.flush()
