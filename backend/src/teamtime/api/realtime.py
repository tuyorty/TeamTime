"""Realtime (ADR 0003): одно LISTEN-соединение на процесс API, раздача событий по SSE."""

from __future__ import annotations

import asyncio
import contextlib
import json
from collections.abc import AsyncIterator
from itertools import count
from typing import Any

import asyncpg

from teamtime.core.logging import get_logger
from teamtime.services.events import CHANNEL

log = get_logger(__name__)

PING_SECONDS = 15
QUEUE_SIZE = 100


class Broadcaster:
    def __init__(self, dsn: str) -> None:
        self._dsn = dsn.replace("postgresql+asyncpg://", "postgresql://")
        self._subscribers: set[asyncio.Queue[dict[str, Any]]] = set()
        self._conn: asyncpg.Connection | None = None
        self._task: asyncio.Task[None] | None = None
        self._ids = count(1)
        self._stopping = asyncio.Event()

    @property
    def subscribers(self) -> int:
        return len(self._subscribers)

    async def start(self) -> None:
        self._task = asyncio.create_task(self._run(), name="teamtime-listen")

    async def stop(self) -> None:
        self._stopping.set()
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
        if self._conn and not self._conn.is_closed():
            await self._conn.close()

    async def _run(self) -> None:
        """Держать LISTEN; при обрыве переподключиться и разослать ``resync``."""
        delay = 1.0
        while not self._stopping.is_set():
            try:
                self._conn = await asyncpg.connect(self._dsn)
                await self._conn.add_listener(CHANNEL, self._on_notify)
                log.info("realtime.listening", channel=CHANNEL)
                self.publish({"type": "resync"})
                delay = 1.0
                while not self._stopping.is_set() and not self._conn.is_closed():
                    await asyncio.sleep(5)
                    await self._conn.execute("SELECT 1")
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.warning("realtime.reconnect", error=str(exc), delay=delay)
                await asyncio.sleep(delay)
                delay = min(delay * 2, 30)

    def _on_notify(self, _conn: object, _pid: int, _channel: str, payload: str) -> None:
        try:
            event = json.loads(payload)
        except json.JSONDecodeError:
            event = {"type": "unknown"}
        self.publish(event)

    def publish(self, event: dict[str, Any]) -> None:
        event = {"id": next(self._ids), **event}
        for queue in list(self._subscribers):
            if queue.full():
                # Медленный клиент: сбросить очередь и попросить перезапросить всё.
                while not queue.empty():
                    queue.get_nowait()
                queue.put_nowait({"id": event["id"], "type": "resync"})
            else:
                queue.put_nowait(event)

    async def stream(self) -> AsyncIterator[str]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(QUEUE_SIZE)
        self._subscribers.add(queue)
        try:
            yield "retry: 3000\n\n"
            yield _format({"id": 0, "type": "hello"})
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=PING_SECONDS)
                except TimeoutError:
                    yield ": ping\n\n"
                    continue
                yield _format(event)
        finally:
            self._subscribers.discard(queue)


def _format(event: dict[str, Any]) -> str:
    data = json.dumps(event, ensure_ascii=False, default=str)
    return f"id: {event.get('id', 0)}\nevent: {event.get('type', 'message')}\ndata: {data}\n\n"
