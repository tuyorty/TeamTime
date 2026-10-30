"""Фабрика приложения FastAPI."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from teamtime import __version__
from teamtime.api.realtime import Broadcaster
from teamtime.api.routers import admin, auth, events, export, finance, read, workflows
from teamtime.core import clock
from teamtime.core.config import Settings, get_settings
from teamtime.core.logging import configure_logging, get_logger
from teamtime.db.session import get_sessionmaker

log = get_logger(__name__)

TAGS = [
    {"name": "экраны", "description": "Данные для экранов сайта: всё уже посчитано на сервере."},
    {"name": "сотрудники", "description": "Справочник и карточки."},
    {"name": "сообщения", "description": "Исходные сообщения, версии, инбокс."},
    {"name": "экспорт", "description": "CSV и XLSX."},
    {
        "name": "админка",
        "description": "Правки и настройки. Нужна сессия админа и X-Requested-With.",
    },
    {"name": "режим админа", "description": "Вход по паролю из .env."},
    {"name": "демо", "description": "Эмулятор чата (только DEMO=1)."},
    {"name": "служебное", "description": "Healthcheck, мета, события, поиск, аудит."},
]


def create_app(settings: Settings | None = None, *, realtime: bool = True) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level, settings.log_format)
    if settings.demo_now is not None:
        clock.freeze(settings.demo_now)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = create_async_engine(settings.database_url, pool_pre_ping=True)
        app.state.engine = engine
        app.state.sessionmaker = get_sessionmaker(engine)
        app.state.broadcaster = Broadcaster(settings.database_url)
        if realtime:
            await app.state.broadcaster.start()
        log.info("api.started", version=__version__, demo=settings.demo)
        if settings.admin_enabled and not settings.session_secret:
            log.warning(
                "api.session_secret_missing",
                detail="SESSION_SECRET не задан: ключ случайный, вход сбросится при перезапуске",
            )
        try:
            yield
        finally:
            await app.state.broadcaster.stop()
            await engine.dispose()
            log.info("api.stopped")

    app = FastAPI(
        title="xTime API",
        version=__version__,
        description=(
            "Таблица команды из сообщений Telegram: планы, дейлики, отчёты.\n\n"
            "Длительности — целые секунды (усечены), время суток — секунды от полуночи. "
            "Чтение открыто без входа, изменения требуют режима админа."
        ),
        openapi_url="/api/v1/openapi.json",
        docs_url="/api/v1/docs",
        redoc_url=None,
        openapi_tags=TAGS,
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/v1/health", tags=["служебное"], summary="Проверка живости и доступа к БД")
    async def health(request: Request) -> JSONResponse:
        try:
            async with request.app.state.engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            db = "ok"
        except Exception as exc:  # pragma: no cover — показываем причину в healthcheck
            db = f"error: {exc.__class__.__name__}"
        ok = db == "ok"
        return JSONResponse(
            {
                "status": "ok" if ok else "degraded",
                "version": __version__,
                "db": db,
                "subscribers": request.app.state.broadcaster.subscribers,
            },
            status_code=200 if ok else 503,
        )

    for router in (
        read.router,
        auth.router,
        admin.router,
        export.router,
        events.router,
        workflows.router,
        finance.router,
    ):
        app.include_router(router, prefix="/api/v1")
    if settings.demo:
        from teamtime.api.routers import demo

        app.include_router(demo.router, prefix="/api/v1")
    return app


app = create_app()
