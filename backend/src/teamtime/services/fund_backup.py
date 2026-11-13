"""Полная зашифрованная копия: проверяем целостность до распаковки и доставки."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import struct
import tarfile
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

MAGIC = b"XTIME-BACKUP-1\x00"
CHUNK = 4 * 1024 * 1024
DELIVERY_PART = 45 * 1024 * 1024


def read_key(path: Path) -> bytes:
    key = base64.b64decode(path.read_bytes().strip(), validate=True)
    if len(key) != 32:
        raise ValueError("Ключ резервной копии должен содержать 32 случайных байта в Base64")
    return key


def encrypt(source: Path, target: Path, key: bytes) -> None:
    """Каждый блок и признак конца аутентифицированы; nonce уникален внутри архива."""
    cipher = AESGCM(key)
    prefix = os.urandom(8)
    header = MAGIC + prefix
    with source.open("rb") as raw, target.open("xb") as output:
        os.chmod(target, 0o600)
        output.write(header)
        for index in range(2**32):
            block = raw.read(CHUNK)
            marker = b"\x01" if block else b"\x00"
            counter = struct.pack(">I", index)
            encrypted = cipher.encrypt(prefix + counter, block, header + counter + marker)
            output.write(marker + struct.pack(">I", len(encrypted)) + encrypted)
            if not block:
                break
        else:
            raise ValueError("Копия превышает ограничение формата")


def decrypt(source: Path, target: Path, key: bytes) -> None:
    cipher = AESGCM(key)
    with source.open("rb") as raw, target.open("xb") as output:
        os.chmod(target, 0o600)
        header = raw.read(len(MAGIC) + 8)
        if not header.startswith(MAGIC) or len(header) != len(MAGIC) + 8:
            raise ValueError("Неизвестный формат копии")
        prefix = header[-8:]
        for index in range(2**32):
            marker = raw.read(1)
            size_bytes = raw.read(4)
            if marker not in {b"\x00", b"\x01"} or len(size_bytes) != 4:
                raise ValueError("Копия оборвана")
            length = struct.unpack(">I", size_bytes)[0]
            if not 16 <= length <= CHUNK + 16:
                raise ValueError("Некорректная длина блока")
            encrypted = raw.read(length)
            if len(encrypted) != length:
                raise ValueError("Копия оборвана")
            counter = struct.pack(">I", index)
            block = cipher.decrypt(prefix + counter, encrypted, header + counter + marker)
            if marker == b"\x00":
                if block or raw.read(1):
                    raise ValueError("Некорректное завершение копии")
                return
            output.write(block)
        raise ValueError("Нет завершающего блока")


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def pack(source: Path, destination: Path, key_path: Path) -> Path:
    """Каталог содержит database.dump, конфигурацию запуска и версию; ключ хранится отдельно."""
    root = source.resolve()
    if not (root / "database.dump").is_file():
        raise ValueError("Нет database.dump")
    if key_path.resolve().is_relative_to(root):
        raise ValueError("Ключ нельзя включать в собственную копию")
    files = sorted(p for p in root.rglob("*") if p.is_file())
    if any(p.is_symlink() or not p.resolve().is_relative_to(root) for p in files):
        raise ValueError("Символические ссылки в копии запрещены")
    destination.mkdir(parents=True, exist_ok=False)
    os.chmod(destination, 0o700)
    with TemporaryDirectory(prefix="xtime-backup-") as tmp:
        tar_path = Path(tmp) / "full.tar.gz"
        with tarfile.open(tar_path, "w:gz") as archive:
            for path in files:
                archive.add(path, arcname=path.relative_to(root).as_posix(), recursive=False)
        encrypted = Path(tmp) / "full.enc"
        encrypt(tar_path, encrypted, read_key(key_path))
        manifest: dict[str, Any] = {"format": 1, "sha256": sha256(encrypted), "parts": []}
        with encrypted.open("rb") as stream:
            index = 1
            while block := stream.read(DELIVERY_PART):
                part = destination / f"xtime-backup.part{index:04d}"
                part.write_bytes(block)
                os.chmod(part, 0o600)
                manifest["parts"].append(
                    {"name": part.name, "bytes": len(block), "sha256": sha256(part)}
                )
                index += 1
    manifest_path = destination / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    os.chmod(manifest_path, 0o600)
    return manifest_path


def unpack(source: Path, destination: Path, key_path: Path) -> None:
    """Восстановление только в новый каталог; проверка всех частей до любых файлов назначения."""
    manifest = json.loads((source / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("format") != 1 or not manifest.get("parts"):
        raise ValueError("Неизвестный манифест")
    if destination.exists():
        raise ValueError("Каталог восстановления уже существует; укажите новый")
    with TemporaryDirectory(prefix="xtime-restore-") as tmp:
        encrypted = Path(tmp) / "full.enc"
        with encrypted.open("xb") as stream:
            for index, part in enumerate(manifest["parts"], 1):
                if part["name"] != f"xtime-backup.part{index:04d}":
                    raise ValueError("Нарушен порядок частей")
                path = source / part["name"]
                if (
                    path.is_symlink()
                    or path.stat().st_size != part["bytes"]
                    or sha256(path) != part["sha256"]
                ):
                    raise ValueError("Часть копии повреждена")
                with path.open("rb") as raw:
                    while block := raw.read(CHUNK):
                        stream.write(block)
        if sha256(encrypted) != manifest["sha256"]:
            raise ValueError("Контрольная сумма архива не совпала")
        tar_path = Path(tmp) / "full.tar.gz"
        decrypt(encrypted, tar_path, read_key(key_path))
        with tarfile.open(tar_path) as archive:
            members = archive.getmembers()
            if not any(m.name == "database.dump" for m in members):
                raise ValueError("В копии нет базы данных")
            for item in members:
                path = Path(item.name)
                if not item.isfile() or path.is_absolute() or ".." in path.parts:
                    raise ValueError("Недопустимый путь в копии")
            destination.mkdir(parents=True, mode=0o700)
            archive.extractall(destination, members=members, filter="data")


async def alert_failure(cycle: str) -> None:
    """Сбой подготовки тоже требует сообщения; повтор одного цикла не рассылает его снова."""
    from aiogram import Bot
    from sqlalchemy import select
    from sqlalchemy.dialects.postgresql import insert

    from teamtime.bot.app import _session
    from teamtime.core import clock
    from teamtime.core.config import get_settings
    from teamtime.db.fund import FundMember
    from teamtime.db.fund_operations import FundNotification
    from teamtime.db.models import TelegramIdentity
    from teamtime.db.session import session_scope
    from teamtime.services import fund_config

    if not cycle or len(cycle) > 60 or not all(c.isalnum() or c in "_-" for c in cycle):
        raise ValueError("Некорректный цикл копии")
    config = get_settings()
    if config.demo or config.bot_token is None:
        return
    async with session_scope() as session:
        options = await fund_config.load(session)
        ids = set(options.technical_employee_ids)
        ids.update(
            await session.scalars(
                select(FundMember.employee_id).where(FundMember.active, FundMember.leader)
            )
        )
        recipients = list(
            await session.scalars(
                select(TelegramIdentity).where(
                    TelegramIdentity.employee_id.in_(ids),
                    TelegramIdentity.linked_at.is_not(None),
                    TelegramIdentity.removed_at.is_(None),
                    TelegramIdentity.dm_chat_id.is_not(None),
                )
            )
        )
    bot = Bot(config.bot_token.get_secret_value(), session=_session(config))
    try:
        for recipient in recipients:
            async with session_scope() as session:
                identifier = await session.scalar(
                    insert(FundNotification)
                    .values(
                        employee_id=recipient.employee_id,
                        cycle=f"backup-error:{cycle}",
                        attempted_at=clock.now(),
                    )
                    .on_conflict_do_nothing()
                    .returning(FundNotification.id)
                )
                await session.commit()
                if identifier is None:
                    continue
                record = await session.get(FundNotification, identifier)
                assert record is not None
                try:
                    assert recipient.dm_chat_id is not None
                    await bot.send_message(
                        recipient.dm_chat_id,
                        "⚠️ Полная резервная копия xTime не завершена. "
                        "Проверьте журнал службы резервного копирования: подготовку, "
                        "шифрование и доставку всех частей. "
                        "Повтор этого цикла не дублирует сообщение.",
                    )
                except Exception as exc:
                    record.error = type(exc).__name__
                else:
                    record.sent_at = clock.now()
    finally:
        await bot.session.close()


async def deliver(source: Path, cycle: str) -> int:
    """Отправляем только шифротекст, по одной попытке на часть и адресата, без polling."""
    from aiogram import Bot
    from aiogram.types import FSInputFile
    from sqlalchemy import select
    from sqlalchemy.dialects.postgresql import insert

    from teamtime.bot.app import _session
    from teamtime.core import clock
    from teamtime.core.config import get_settings
    from teamtime.db.fund import FundMember
    from teamtime.db.fund_operations import FundNotification
    from teamtime.db.models import TelegramIdentity
    from teamtime.db.session import session_scope
    from teamtime.services import fund_config

    config = get_settings()
    if config.bot_token is None or config.demo:
        raise ValueError("Доставка копии требует настроенного боевого бота")
    manifest = json.loads((source / "manifest.json").read_text(encoding="utf-8"))
    paths = [source / "manifest.json"]
    for index, part in enumerate(manifest["parts"], 1):
        if part["name"] != f"xtime-backup.part{index:04d}":
            raise ValueError("Некорректное имя части")
        path = source / part["name"]
        if sha256(path) != part["sha256"] or path.stat().st_size > DELIVERY_PART:
            raise ValueError("Часть повреждена или слишком велика")
        paths.append(path)
    async with session_scope() as session:
        options = await fund_config.load(session)
        ids = set(options.technical_employee_ids)
        ids.update(
            await session.scalars(
                select(FundMember.employee_id).where(FundMember.leader, FundMember.active)
            )
        )
        recipients = list(
            await session.scalars(
                select(TelegramIdentity).where(
                    TelegramIdentity.employee_id.in_(ids),
                    TelegramIdentity.linked_at.is_not(None),
                    TelegramIdentity.removed_at.is_(None),
                    TelegramIdentity.dm_chat_id.is_not(None),
                )
            )
        )
        if (
            {r.employee_id for r in recipients} != ids
            or not options.technical_employee_ids
            or not ids
        ):
            raise ValueError("Руководитель и технический администратор должны начать личку с ботом")
    failures = 0
    bot = Bot(config.bot_token.get_secret_value(), session=_session(config))
    try:
        for recipient in recipients:
            for index, path in enumerate(paths):
                async with session_scope() as session:
                    token = f"backup:{cycle}:{index}"
                    if len(token) > 100:
                        raise ValueError("Слишком длинный идентификатор копии")
                    notification_id = await session.scalar(
                        insert(FundNotification)
                        .values(
                            employee_id=recipient.employee_id, cycle=token, attempted_at=clock.now()
                        )
                        .on_conflict_do_nothing()
                        .returning(FundNotification.id)
                    )
                    await session.commit()
                    if notification_id is None:
                        old = await session.scalar(
                            select(FundNotification).where(
                                FundNotification.employee_id == recipient.employee_id,
                                FundNotification.cycle == token,
                            )
                        )
                        failures += int(old is None or old.sent_at is None)
                        continue
                    try:
                        assert recipient.dm_chat_id is not None
                        await bot.send_document(
                            recipient.dm_chat_id,
                            FSInputFile(path),
                            caption=(
                                f"Зашифрованная копия xTime · {cycle} · "
                                f"файл {index + 1}/{len(paths)}. "
                                f"Сохраните все файлы вместе. Ключ хранится отдельно."
                            ),
                        )
                    except Exception as exc:
                        failures += 1
                        record = await session.get(FundNotification, notification_id)
                        assert record is not None
                        record.error = type(exc).__name__
                    else:
                        record = await session.get(FundNotification, notification_id)
                        assert record is not None
                        record.sent_at = clock.now()
        if failures:
            for recipient in recipients:
                async with session_scope() as session:
                    alert = await session.scalar(
                        insert(FundNotification)
                        .values(
                            employee_id=recipient.employee_id,
                            cycle=f"backup-error:{cycle}",
                            attempted_at=clock.now(),
                        )
                        .on_conflict_do_nothing()
                        .returning(FundNotification.id)
                    )
                    await session.commit()
                    if alert is None:
                        continue
                    record = await session.get(FundNotification, alert)
                    assert record is not None
                    try:
                        assert recipient.dm_chat_id is not None
                        await bot.send_message(
                            recipient.dm_chat_id,
                            "⚠️ Полная копия xTime доставлена не полностью. "
                            "Проверьте журнал службы резервного копирования и наличие всех частей. "
                            "Автоматического повтора отправки не будет.",
                        )
                    except Exception as exc:
                        record.error = type(exc).__name__
                    else:
                        record.sent_at = clock.now()
    finally:
        await bot.session.close()
    if failures:
        raise ValueError(
            "Часть копии не доставлена. Автоповтор отключён; проверьте журнал доставки"
        )
    return len(recipients)
