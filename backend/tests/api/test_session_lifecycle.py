"""Ответ API отправляется только после фиксации транзакции, включая ошибки commit."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock

import httpx
from fastapi import FastAPI, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.types import Message, Receive, Scope, Send

from teamtime.api.deps import SessionDep


def transaction_client(
    *, fail_commit: bool = False, reject_handler: bool = False
) -> tuple[httpx.AsyncClient, list[str]]:
    """Настоящий ASGI-цикл и dependency приложения с управляемой сессией без БД."""
    events: list[str] = []
    session = AsyncMock(spec=AsyncSession)

    async def commit() -> None:
        events.append("commit.start")
        await asyncio.sleep(0)
        if fail_commit:
            raise RuntimeError("commit failed")
        events.append("commit.done")

    async def rollback() -> None:
        events.append("rollback")

    session.commit.side_effect = commit
    session.rollback.side_effect = rollback

    @asynccontextmanager
    async def maker() -> AsyncIterator[AsyncSession]:
        events.append("session.open")
        try:
            yield session
        finally:
            events.append("session.close")

    app = FastAPI()
    app.state.sessionmaker = maker

    @app.post("/records")
    async def create_record(db: SessionDep) -> dict[str, bool]:
        events.append("handler")
        await db.flush()
        if reject_handler:
            raise HTTPException(status_code=409, detail="conflict")
        return {"saved": True}

    async def capture_response(scope: Scope, receive: Receive, send: Send) -> None:
        async def capture(message: Message) -> None:
            if message["type"] == "http.response.start":
                events.append(f"response.{message['status']}")
            await send(message)

        await app(scope, receive, capture)

    client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=capture_response, raise_app_exceptions=False),
        base_url="http://test",
    )
    return client, events


async def test_success_response_starts_after_commit_and_session_close() -> None:
    client, events = transaction_client()
    async with client:
        response = await client.post("/records")

    assert response.status_code == 200
    assert response.json() == {"saved": True}
    assert events == [
        "session.open",
        "handler",
        "commit.start",
        "commit.done",
        "session.close",
        "response.200",
    ]


async def test_commit_failure_rolls_back_before_error_response() -> None:
    client, events = transaction_client(fail_commit=True)
    async with client:
        response = await client.post("/records")

    assert response.status_code == 500
    assert events == [
        "session.open",
        "handler",
        "commit.start",
        "rollback",
        "session.close",
        "response.500",
    ]


async def test_handler_failure_rolls_back_without_commit() -> None:
    client, events = transaction_client(reject_handler=True)
    async with client:
        response = await client.post("/records")

    assert response.status_code == 409
    assert events == [
        "session.open",
        "handler",
        "rollback",
        "session.close",
        "response.409",
    ]
