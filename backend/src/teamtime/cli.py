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
system_app = typer.Typer(help="Состояние служебных процессов.", no_args_is_help=True)
app.add_typer(system_app, name="system")
backup_app = typer.Typer(help="Полная зашифрованная копия и восстановление.", no_args_is_help=True)
app.add_typer(backup_app, name="backup")


@backup_app.command("pack")
def backup_pack(source: Path, destination: Path, key_file: Path) -> None:
    """Упаковать подготовленный каталог. Секреты и ключ не выводятся."""
    from teamtime.services.fund_backup import pack

    typer.echo(str(pack(source, destination, key_file)))


@backup_app.command("unpack")
def backup_unpack(source: Path, destination: Path, key_file: Path) -> None:
    """Проверить и расшифровать в новый каталог, не изменяя рабочую БД."""
    from teamtime.services.fund_backup import unpack

    unpack(source, destination, key_file)
    typer.echo("Копия проверена и расшифрована. База данных не изменялась.")


@backup_app.command("deliver")
def backup_deliver(source: Path, cycle: str) -> None:
    """Доставить зашифрованную копию назначенным ответственным, не запуская polling."""
    import asyncio

    from teamtime.services.fund_backup import deliver

    typer.echo(f"Копия доставлена. Получателей: {asyncio.run(deliver(source, cycle))}")


@system_app.command("backup")
def record_backup(state: str = typer.Option("ok", help="ok или error")) -> None:
    """Записать результат скрипта резервного копирования без содержимого копии."""
    import asyncio

    from teamtime.db.session import session_scope
    from teamtime.services.diagnostics import set_service

    if state not in {"ok", "error"}:
        raise typer.BadParameter("Допустимы ok или error")

    async def go() -> None:
        async with session_scope() as session:
            await set_service(
                session,
                "backup",
                state,
                success=state == "ok",
                error_code="BackupFailed" if state == "error" else None,
            )

    asyncio.run(go())


@backup_app.command("alert")
def backup_alert(cycle: str) -> None:
    """Однократное сообщение ответственным о сбое подготовки или доставки копии."""
    import asyncio

    from teamtime.services.fund_backup import alert_failure

    asyncio.run(alert_failure(cycle))


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


@import_app.command("fund")
def import_fund(
    path: Path = typer.Argument(..., exists=True, dir_okay=False),
    actor: int = typer.Option(..., help="Внутренний ID руководителя, подтвердившего пакет"),
    expected_digest: str = typer.Option(
        "", help="Хеш проверенного пакета; без него только проверка"
    ),
) -> None:
    """Проверить пакет исторических финансов; применить только с хешем проверенной версии."""
    import asyncio
    import json

    from teamtime.db.session import session_scope
    from teamtime.importer import fund

    package = fund.Package.model_validate_json(path.read_text(encoding="utf-8-sig"))

    async def run() -> dict[str, object]:
        async with session_scope() as session:
            if expected_digest:
                return await fund.apply(session, actor, package, expected_digest)
            return await fund.inspect(session, actor, package)

    typer.echo(json.dumps(asyncio.run(run()), ensure_ascii=False, indent=2))


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
