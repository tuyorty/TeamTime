"""Фабрика приложения FastAPI."""

from __future__ import annotations

from fastapi import FastAPI

from teamtime import __version__
from teamtime.core.config import get_settings
from teamtime.core.logging import configure_logging


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_format)
    app = FastAPI(
        title="TeamTime API",
        version=__version__,
        description="Табель команды из сообщений Telegram: планы, дейлики, отчёты.",
        openapi_url="/api/v1/openapi.json",
        docs_url="/api/v1/docs",
        redoc_url=None,
    )

    @app.get("/api/v1/health", tags=["служебное"], summary="Проверка живости")
    async def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    return app


app = create_app()
