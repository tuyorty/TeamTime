from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from teamtime.db.models import RawMessage, RawMessageVersion, Source
from teamtime.importer.telegram import (
    ExportFormatError,
    bot_api_chat_id,
    flatten_text,
    import_export,
    load_export,
)
from teamtime.services.facts import current_dailies, current_plans
from teamtime.services.ingest import ingest
from tests import factories as f

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "telegram_export.json"


def export() -> dict:
    return load_export(FIXTURE.read_bytes())


def test_flatten_text_handles_both_formats() -> None:
    assert flatten_text("просто") == "просто"
    assert flatten_text(["a", {"type": "bold", "text": "b"}, "c"]) == "abc"
    assert flatten_text(None) == ""


def test_chat_id_matches_bot_api() -> None:
    assert bot_api_chat_id(1234567890, "private_supergroup") == -1001234567890
    assert bot_api_chat_id(-1001234567890, "private_supergroup") == -1001234567890


@pytest.mark.parametrize("data", [b"not json", b"[]", b'{"name": "x"}'])
def test_rejects_non_export(data: bytes) -> None:
    with pytest.raises(ExportFormatError):
        load_export(data)


@pytest.mark.db
async def test_import_uses_topics_and_is_idempotent(session: AsyncSession) -> None:
    await f.employee(session, "Иванов И.И.", tg_id=501)
    report = await import_export(session, export())
    assert report.chat_id == -1001234567890
    assert report.topics == {2: "Расписание", 3: "Дейлики"}
    assert report.total == 6
    assert report.imported == 4  # расписание, два дейлика и реплика в теме дейликов
    assert report.skipped == 2  # болтовня вне тем и фото без текста
    assert report.statuses == {"ok": 3, "failed": 1}

    plans = await current_plans(session, date(2026, 10, 19), date(2026, 10, 25))
    assert len(plans) == 1
    dailies = await current_dailies(session, date(2026, 10, 19), date(2026, 10, 20))
    assert {d.work_date: d.efficiency for d in dailies} == {
        date(2026, 10, 19): 90,
        date(2026, 10, 20): 80,
    }

    raw = await session.scalar(select(RawMessage).where(RawMessage.message_id == 13))
    assert raw is not None and raw.thread_id == 3  # тема найдена по цепочке ответов
    assert raw.source is Source.IMPORT

    again = await import_export(session, export())
    assert again.imported == 0
    assert again.unchanged == 4
    assert await session.scalar(select(func.count()).select_from(RawMessageVersion)) == 4


@pytest.mark.db
async def test_import_after_bot_does_not_duplicate(session: AsyncSession) -> None:
    await f.employee(session, "Иванов И.И.", tg_id=501)
    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    original = data["messages"][3]["text"].replace("90%", "70%")
    await ingest(
        session,
        f.message(original, author=501, message_id=11, thread=3),
    )
    report = await import_export(session, data)
    assert report.imported == 4  # сообщение 11 пришло с новым текстом — это правка
    versions = await session.scalar(
        select(func.count())
        .select_from(RawMessageVersion)
        .join(RawMessage)
        .where(RawMessage.message_id == 11)
    )
    assert versions == 2
