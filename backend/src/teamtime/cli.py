"""Командная строка: ``teamtime <группа> <команда>``."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import typer

app = typer.Typer(help="xTime: таблица команды из Telegram.", no_args_is_help=True)
db_app = typer.Typer(help="База данных и миграции.", no_args_is_help=True)
bot_app = typer.Typer(help="Telegram-бот.", no_args_is_help=True)
demo_app = typer.Typer(help="Демо-данные и эмулятор.", no_args_is_help=True)
app.add_typer(db_app, name="db")
app.add_typer(bot_app, name="bot")
app.add_typer(demo_app, name="demo")


def _alembic_ini() -> Path:
    """alembic.ini рядом с исходниками (editable-установка) или в рабочей папке (Docker)."""
    for candidate in (Path(__file__).resolve().parents[2], Path.cwd()):
        if (candidate / "alembic.ini").is_file():
            return candidate / "alembic.ini"
    raise typer.BadParameter("Не найден alembic.ini: запустите из папки backend/")


@app.callback()
def main() -> None:
    """Общая настройка логов для всех команд."""
    from teamtime.core.config import get_settings
    from teamtime.core.logging import configure_logging

    settings = get_settings()
    configure_logging(settings.log_level, settings.log_format)


@app.command()
def version() -> None:
    """Показать версию."""
    from teamtime import __version__

    typer.echo(__version__)


import_app = typer.Typer(help="Импорт истории.", no_args_is_help=True)
app.add_typer(import_app, name="import")


@import_app.command("telegram")
def import_telegram(
    path: Path = typer.Argument(
        ..., exists=True, dir_okay=False, help="result.json из Telegram Desktop"
    ),
    chat_id: int | None = typer.Option(None, help="Переопределить chat_id (вид Bot API: -100…)"),
    since: datetime | None = typer.Option(
        None, formats=["%Y-%m-%d"], help="Только сообщения с этой даты, например 2026-01-01"
    ),
) -> None:
    """Импортировать экспорт чата. Повторный запуск ничего не дублирует."""
    import asyncio
    import json as _json

    from teamtime.db.session import session_scope
    from teamtime.importer.telegram import ExportFormatError, import_export, load_export

    raw = path.read_bytes()

    async def go() -> dict[str, object]:
        async with session_scope() as session:
            report = await import_export(
                session, load_export(raw), chat_id=chat_id, since=since.date() if since else None
            )
            return report.as_dict()

    try:
        result = asyncio.run(go())
    except ExportFormatError as exc:
        raise typer.BadParameter(str(exc)) from exc
    typer.echo(_json.dumps(result, ensure_ascii=False, indent=2))


@db_app.command("upgrade")
def db_upgrade(revision: str = typer.Argument("head")) -> None:
    """Применить миграции (по умолчанию до последней)."""
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(_alembic_ini()))
    command.upgrade(cfg, revision)


@bot_app.command("run")
def bot_run() -> None:
    """Запустить бота (long polling). Без BOT_TOKEN завершается с кодом 0."""
    import asyncio

    from teamtime.bot.app import run
    from teamtime.core.config import get_settings

    asyncio.run(run(get_settings()))


@bot_app.command("check")
def bot_check() -> None:
    """Проверить связь с Telegram и токен тем же путём, что и бот (с TELEGRAM_PROXY, если задан)."""
    import asyncio

    from teamtime.bot.app import check
    from teamtime.core.config import get_settings

    ok, message = asyncio.run(check(get_settings()))
    typer.echo(message)
    raise typer.Exit(0 if ok else 1)


@demo_app.command("seed")
def demo_seed(
    if_empty: bool = typer.Option(False, "--if-empty", help="Только если в базе нет сотрудников."),
    force: bool = typer.Option(False, "--force", help="Очистить данные и загрузить заново."),
    weeks: int = typer.Option(9, min=1, max=26, help="Сколько недель истории."),
    seed: int = typer.Option(7, help="Зерно генератора: одно и то же даёт одни и те же данные."),
) -> None:
    """Загрузить вымышленных сотрудников и несколько недель сообщений."""
    import asyncio

    from teamtime.core import clock
    from teamtime.core.config import get_settings
    from teamtime.db.session import session_scope
    from teamtime.demo.seed import seed_demo

    if (frozen := get_settings().demo_now) is not None:
        clock.freeze(frozen)

    async def go() -> bool:
        async with session_scope() as session:
            return await seed_demo(session, weeks=weeks, seed=seed, force=force, if_empty=if_empty)

    try:
        done = asyncio.run(go())
    except RuntimeError as exc:
        raise typer.BadParameter(str(exc)) from exc
    typer.echo("Демо-данные загружены." if done else "В базе уже есть данные, демо не загружено.")


if __name__ == "__main__":
    app()
