"""Общие фикстуры. Тесты с БД помечены ``db`` и требуют TEST_DATABASE_URL.

Схема создаётся миграциями Alembic (так тесты заодно проверяют миграции), а между тестами
таблицы очищаются TRUNCATE.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from teamtime.core import clock

TEST_DB = os.environ.get("TEST_DATABASE_URL")
BACKEND = Path(__file__).resolve().parents[1]
# Понедельник 26.10.2026, 12:00 по Екатеринбургу.
NOW = datetime(2026, 10, 26, 7, 0, tzinfo=UTC)
# Чат вымышленной команды: в каждом тесте с БД уже разрешён админом. Сообщения из любых
# других чатов бот не принимает — это проверяют отдельные тесты.
TEAM_CHAT = -1001234567890


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if TEST_DB:
        return
    skip = pytest.mark.skip(reason="нужна PostgreSQL: задайте TEST_DATABASE_URL (make dev-db)")
    for item in items:
        if "db" in item.keywords:
            item.add_marker(skip)


@pytest.fixture(autouse=True)
def frozen_clock() -> Iterator[datetime]:
    clock.freeze(NOW)
    yield NOW
    clock.freeze(None)


@pytest.fixture(scope="session")
async def engine() -> AsyncIterator[AsyncEngine]:
    assert TEST_DB, "TEST_DATABASE_URL не задан"
    eng = create_async_engine(TEST_DB)
    async with eng.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))

        def upgrade(sync_conn: object) -> None:
            from alembic import command
            from alembic.config import Config

            cfg = Config(str(BACKEND / "alembic.ini"))
            cfg.attributes["connection"] = sync_conn
            cfg.attributes["skip_logging"] = True
            command.upgrade(cfg, "head")

        await conn.run_sync(upgrade)
    yield eng
    await eng.dispose()


TABLES = (
    "audit_log, app_settings, daily_tasks, daily_intervals, dailies, sprint_tasks, plan_days, "
    "schedule_plans, parse_results, raw_message_versions, raw_messages, day_statuses, "
    "topic_bindings, bot_chats, telegram_identities, daily_reminders, employees"
)


@pytest.fixture
async def maker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    async with engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {TABLES} RESTART IDENTITY CASCADE"))
        await conn.execute(
            text(
                "INSERT INTO bot_chats (chat_id, title, is_forum, approved) "
                "VALUES (:id, 'Вымышленная команда', true, true)"
            ),
            {"id": TEAM_CHAT},
        )
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest.fixture
async def session(maker: async_sessionmaker[AsyncSession]) -> AsyncIterator[AsyncSession]:
    async with maker() as s:
        yield s
        await s.rollback()
