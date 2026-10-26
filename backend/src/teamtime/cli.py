"""Командная строка: ``teamtime <группа> <команда>``."""

from __future__ import annotations

from pathlib import Path

import typer

app = typer.Typer(help="TeamTime: табель команды из Telegram.", no_args_is_help=True)
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


@app.command()
def version() -> None:
    """Показать версию."""
    from teamtime import __version__

    typer.echo(__version__)


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


@demo_app.command("seed")
def demo_seed(
    if_empty: bool = typer.Option(False, "--if-empty", help="Только если в базе нет сотрудников."),
    force: bool = typer.Option(False, "--force", help="Очистить данные и загрузить заново."),
) -> None:
    """Загрузить вымышленных сотрудников и несколько недель сообщений."""
    typer.echo("Демо-данные ещё не реализованы.")


if __name__ == "__main__":
    app()
