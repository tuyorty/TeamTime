"""SSE-поток событий для сайта."""

from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

router = APIRouter(tags=["служебное"])


@router.get(
    "/events",
    summary="Поток событий (Server-Sent Events)",
    description=(
        "События: `message.ingested`, `daily.changed`, `plan.changed`, `status.changed`, "
        "`employee.changed`, `identity.changed`, `inbox.changed`, `settings.changed`, `resync`. "
        "Данные события — только идентификаторы; клиент перезапрашивает нужные экраны."
    ),
    response_class=StreamingResponse,
)
async def events(request: Request) -> StreamingResponse:
    broadcaster = request.app.state.broadcaster

    async def body() -> AsyncIterator[str]:
        async for chunk in broadcaster.stream():
            if await request.is_disconnected():
                break
            yield chunk

    return StreamingResponse(
        body(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
