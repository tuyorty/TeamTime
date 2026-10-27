"""Бот на поддельном Telegram: реакции в теме, исправления в личке, команды, правки сообщений."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import date

import pytest
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.methods import DeleteMessage, SendMessage, SetMessageReaction
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from teamtime.bot.app import build_dispatcher
from teamtime.bot.keyboards import FixCb, MenuCb, StatusCb
from teamtime.calc import StatusKind
from teamtime.core.config import Settings
from teamtime.db.models import DayStatus, ParseResultRow, RawMessage, Resolution, TopicBinding
from teamtime.services.facts import current_dailies, current_plans
from tests import factories as f
from tests.bot.fake_telegram import STRANGERS, FakeSession, Telegram
from tests.conftest import TEST_DB

pytestmark = pytest.mark.db


_DISPATCHER: dict[str, object] = {}


def dispatcher(maker: async_sessionmaker[AsyncSession]) -> Dispatcher:
    """Роутеры aiogram подключаются один раз — диспетчер общий на все тесты модуля.

    Сессии берутся из общего движка, поэтому TRUNCATE между тестами его не ломает.
    """
    if "dp" not in _DISPATCHER:
        assert TEST_DB
        config = Settings(
            database_url=TEST_DB,
            bot_token=SecretStr("123456:TEST-TOKEN"),
            bot_username="teamtime_test_bot",
        )
        _DISPATCHER["dp"] = build_dispatcher(maker, config)
    dp = _DISPATCHER["dp"]
    assert isinstance(dp, Dispatcher)
    dp.fsm.storage = MemoryStorage()  # без состояний FSM из прошлых тестов
    return dp


@pytest.fixture
async def tg(maker: async_sessionmaker[AsyncSession]) -> AsyncIterator[Telegram]:
    fake = FakeSession()
    bot = Bot("123456:TEST-TOKEN", session=fake)
    async with maker() as s:
        await f.forum(s)
        await f.employee(s, "Иванов И.И.", tg_id=501)
        await f.employee(s, "Петров П.П.")
        await s.commit()
    return Telegram(dispatcher(maker), bot, fake)


def reactions(tg: Telegram) -> list[str]:
    return [c.reaction[0].emoji for c in tg.session.of(SetMessageReaction)]


async def test_schedule_gets_ok_reaction_and_no_reply(tg: Telegram, maker) -> None:
    await tg.group(777, f.schedule_text("Петров П.П."), thread=f.SCHEDULE_THREAD)
    assert reactions(tg) == ["👌"]
    assert tg.session.of(SendMessage) == []
    async with maker() as s:
        plans = await current_plans(s, date(2026, 10, 26), date(2026, 11, 1))
    assert len(plans) == 1


async def test_problem_reply_says_what_and_how_to_fix(tg: Telegram) -> None:
    await tg.group(501, "23.10.2026\n10:00 - 18:00\nс обедом\n- без эффективности")
    assert reactions(tg) == ["🤔"]
    replies = tg.session.of(SendMessage)
    assert len(replies) == 1
    text = replies[0].text
    assert "строка «с обедом» — не понял, что это" in text
    assert "Добавьте строку «Эффективность: 80%»" in text
    assert "Отредактируйте сообщение" in text
    assert "https://t.me/teamtime_test_bot?start=fix_" in text


async def test_unlinked_account_is_not_blamed_on_author(tg: Telegram) -> None:
    await tg.group(888, f.daily_text("23.10.2026"))
    text = tg.session.of(SendMessage)[0].text
    assert "не привязан" in text
    assert "переписывать не нужно" in text
    assert "Отредактируйте" not in text


async def test_chatter_in_topic_is_ignored(tg: Telegram) -> None:
    await tg.group(501, "кто идёт на обед?")
    assert tg.session.calls == []


def _p(text: object) -> dict[str, object]:
    return {"type": "paragraph", "text": text}


DAILY_RICH = {
    "blocks": [
        _p("23.10.2026"),
        _p("10:00 - 18:00"),
        _p(["Эффективность: ", {"type": "bold", "text": "90%"}]),
        {
            "type": "list",
            "items": [
                {"label": "•", "blocks": [_p("сделал управление роботом")]},
                {"label": "•", "blocks": [_p("написал гайд")]},
            ],
        },
        _p({"type": "hashtag", "text": "#дейли", "hashtag": "дейли"}),
    ]
}


async def test_rich_message_with_list_is_parsed(tg: Telegram, maker) -> None:
    """Дейлик со списком Telegram присылает как rich_message без text — разбираем и его."""
    mid = await tg.group(501, "", rich=DAILY_RICH)
    assert reactions(tg) == ["👌"]
    async with maker() as s:
        dailies = await current_dailies(s, date(2026, 10, 23), date(2026, 10, 23))
    assert dailies[0].efficiency == 90
    edited = {**DAILY_RICH, "blocks": [*DAILY_RICH["blocks"][:2], _p("Эффективность: 70%")]}
    await tg.group(501, "", rich=edited, message_id=mid, edit=True)
    async with maker() as s:
        dailies = await current_dailies(s, date(2026, 10, 23), date(2026, 10, 23))
    assert dailies[0].efficiency == 70


async def test_edit_that_fixes_message_removes_warning(tg: Telegram, maker) -> None:
    mid = await tg.group(501, "23.10.2026\n10:00 - 18:00\n- без эффективности")
    await tg.group(501, f.daily_text("23.10.2026", e=80), message_id=mid, edit=True)
    assert reactions(tg) == ["🤔", "✍"]
    assert len(tg.session.of(DeleteMessage)) == 1
    async with maker() as s:
        dailies = await current_dailies(s, date(2026, 10, 23), date(2026, 10, 23))
    assert dailies[0].efficiency == 80
    assert dailies[0].edited


async def test_reaction_failure_falls_back_to_short_reply(tg: Telegram) -> None:
    tg.session.fail_reactions = True
    await tg.group(501, f.daily_text("23.10.2026"))
    assert [m.text for m in tg.session.of(SendMessage)] == ["Принято"]


async def test_bind_requires_chat_admin(tg: Telegram, maker) -> None:
    await tg.group(601, "/bind дейлики", thread=55)
    async with maker() as s:
        assert await s.scalar(select(TopicBinding).where(TopicBinding.thread_id == 55)) is None
    tg.session.admins.add(601)
    await tg.group(601, "/bind дейлики", thread=55)
    async with maker() as s:
        binding = await s.scalar(select(TopicBinding).where(TopicBinding.thread_id == 55))
    assert binding is not None and binding.kind.value == "daily"
    assert "Готово" in tg.session.texts()[-1]


async def test_private_commands(tg: Telegram) -> None:
    await tg.group(501, f.daily_text("26.10.2026", "10:15 - 18:00", 80))
    await tg.private(501, "/today")
    assert "Сегодня, пн, 26 октября" in tg.session.texts()[-1]
    await tg.private(501, "/week")
    week = tg.session.texts()[-1]
    assert "44 неделя" in week and "Иванов И.И." in week
    await tg.private(501, "/me")
    assert "Итого" in tg.session.texts()[-1]
    await tg.private(501, "/who")
    assert "команда" in tg.session.texts()[-1]
    await tg.private(999, "/week")
    assert "не привязан" in tg.session.texts()[-1]


async def test_fix_efficiency_via_deep_link_and_buttons(tg: Telegram, maker) -> None:
    await tg.group(501, "23.10.2026\n10:00 - 18:00\n- без эффективности")
    async with maker() as s:
        parse_id = await s.scalar(select(ParseResultRow.id).where(ParseResultRow.is_latest))
    assert parse_id is not None
    await tg.private(501, f"/start fix_{parse_id}")
    assert "Дейлик за 23.10.2026" in tg.session.texts()[-1]
    await tg.press(501, FixCb(action="eff_set", parse_id=parse_id, value=80).pack())
    async with maker() as s:
        dailies = await current_dailies(s, date(2026, 10, 23), date(2026, 10, 23))
        row = await s.get(ParseResultRow, parse_id)
    assert dailies[0].efficiency == 80
    assert dailies[0].source.value == "manual"
    assert row is not None and row.resolution is Resolution.FIXED


async def test_fix_time_via_fsm(tg: Telegram, maker) -> None:
    await tg.group(501, "23.10.2026\n10:00 - 18:00\n- без эффективности")
    async with maker() as s:
        parse_id = await s.scalar(select(ParseResultRow.id).where(ParseResultRow.is_latest))
    assert parse_id is not None
    await tg.press(501, FixCb(action="time", parse_id=parse_id).pack())
    await tg.private(501, "непонятно")
    assert "Не понял время" in tg.session.texts()[-1]
    await tg.private(501, "11:00 - 19:30")
    async with maker() as s:
        dailies = await current_dailies(s, date(2026, 10, 23), date(2026, 10, 23))
    assert dailies[0].intervals[0].start_sec == 11 * 3600


async def test_someone_else_cannot_fix(tg: Telegram) -> None:
    await tg.group(501, "23.10.2026\n10:00 - 18:00\n- без эффективности")
    await tg.private(502, "/start fix_1")
    assert "не вами" in tg.session.texts()[-1]


async def test_absent_today_and_vacation(tg: Telegram, maker) -> None:
    await tg.press(501, StatusCb(kind="absent").pack())
    await tg.press(501, StatusCb(kind="vacation").pack())
    await tg.private(501, "02.11 - 06.11")
    assert "Отпуск с 02.11 по 06.11: 5 дней" in tg.session.texts()[-1]
    async with maker() as s:
        statuses = list(await s.scalars(select(DayStatus).where(DayStatus.retracted_at.is_(None))))
    kinds = {(st.date, st.kind) for st in statuses}
    assert (date(2026, 10, 26), StatusKind.ABSENT) in kinds
    assert len(statuses) == 6


# --- безопасность: бот публичный, найти и добавить его может кто угодно ----------------------


async def test_foreign_group_cannot_write_plans(tg: Telegram, maker) -> None:
    """Расписание сопоставляется по ФИО — из чужой группы его подменять нельзя."""
    await tg.group(777, f.schedule_text("Петров П.П."), thread=None, chat=STRANGERS)
    await tg.group(777, f.schedule_text("Петров П.П.") + "\n#расписание", chat=STRANGERS)
    assert tg.session.calls == []  # ни реакций, ни ответов
    async with maker() as s:
        assert await current_plans(s, date(2026, 10, 26), date(2026, 11, 1)) == []
        assert await s.scalar(select(RawMessage.id)) is None


async def test_bind_in_new_chat_waits_for_admin_approval(tg: Telegram, maker) -> None:
    tg.session.admins.add(601)
    await tg.group(601, "/bind расписание", thread=11, chat=STRANGERS)
    assert "не разрешён" in tg.session.texts()[-1]
    await tg.group(777, f.schedule_text("Петров П.П."), thread=11, chat=STRANGERS)
    async with maker() as s:
        assert await current_plans(s, date(2026, 10, 26), date(2026, 11, 1)) == []


async def test_team_commands_hidden_from_strangers(tg: Telegram) -> None:
    await tg.group(501, f.daily_text("26.10.2026", "10:15 - 18:00", 80))
    for command in ("/today", "/who"):
        await tg.private(999, command)
        answer = tg.session.texts()[-1]
        assert "не привязан" in answer and "Иванов" not in answer
    sent = len(tg.session.of(SendMessage))
    await tg.group(777, "/today", chat=STRANGERS)
    await tg.group(777, "/who", chat=STRANGERS)
    assert len(tg.session.of(SendMessage)) == sent  # в чужой группе бот молчит
    await tg.press(999, MenuCb(action="today").pack())
    assert "Иванов" not in tg.session.texts()[-1]


async def test_telegram_name_is_text_not_html_in_group_reply(tg: Telegram) -> None:
    evil = '<a href="https://evil.example/login">Подтвердите аккаунт</a>'
    await tg.group(888, f.daily_text("23.10.2026"), name=evil)
    reply = tg.session.texts()[-1]
    assert "&lt;a href=" in reply  # имя показано как текст
    assert '<a href="https://evil' not in reply
