"""Бот на поддельном Telegram: реакции в теме, исправления в личке, команды, правки сообщений."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import date
from unittest.mock import AsyncMock

import pytest
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.methods import DeleteMessage, EditMessageText, SendMessage, SetMessageReaction
from aiohttp_socks import ProxyTimeoutError
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from teamtime.bot.app import build_dispatcher
from teamtime.bot.keyboards import FixCb, MenuCb, PersonalCb, ReportCb, StatusCb
from teamtime.calc import StatusKind
from teamtime.core.config import Settings
from teamtime.db.models import (
    BotDraft,
    DayStatus,
    NotificationPreference,
    ParseResultRow,
    RawMessage,
    Resolution,
    StatusRequest,
    TopicBinding,
)
from teamtime.services import status_requests
from teamtime.services.facts import current_dailies, current_plans
from teamtime.services.settings import load_settings, save_settings
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
            public_url="https://dashboard.example",
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


@pytest.mark.parametrize("feedback", ["reaction", "reply"])
@pytest.mark.parametrize("efficiency", [80, None])
async def test_replayed_update_does_not_repeat_feedback(
    tg: Telegram, maker, feedback, efficiency
) -> None:
    async with maker() as session:
        settings = await load_settings(session)
        settings.bot.feedback = feedback
        await save_settings(session, settings)
        await session.commit()
    text = f.daily_text("23.10.2026", e=efficiency)
    message_id = await tg.group(501, text)
    calls = len(tg.session.calls)
    assert calls > 0
    await tg.group(501, text, message_id=message_id)
    assert len(tg.session.calls) == calls


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
    replies = tg.session.of(SendMessage)
    assert len(replies) == 1
    assert "<b>✅ Дейлик принят</b>" in replies[0].text


@pytest.mark.parametrize("failures", [1, 3])
async def test_proxy_timeout_keeps_daily_without_duplicate_feedback(
    tg: Telegram, maker, monkeypatch, failures: int
) -> None:
    """Тайм-аут после сохранения дейлика не теряет данные и не порождает ответы-дубли."""
    monkeypatch.setattr("teamtime.bot.reactions.sleep", AsyncMock())
    tg.session.reaction_failures = [ProxyTimeoutError("Proxy timed out") for _ in range(failures)]
    text = f.daily_text("23.10.2026")
    message_id = await tg.group(501, text)
    assert len(tg.session.of(SetMessageReaction)) == min(failures + 1, 3)
    assert tg.session.of(SendMessage) == []
    async with maker() as session:
        dailies = await current_dailies(session, date(2026, 10, 23), date(2026, 10, 23))
        assert len(dailies) == 1
        assert dailies[0].efficiency == 80
    calls = len(tg.session.calls)
    await tg.group(501, text, message_id=message_id)
    assert len(tg.session.calls) == calls


async def test_proxy_failure_does_not_repeat_problem_reply(tg: Telegram, monkeypatch) -> None:
    monkeypatch.setattr("teamtime.bot.reactions.sleep", AsyncMock())
    tg.session.reaction_failures = [ProxyTimeoutError("Proxy timed out") for _ in range(3)]
    text = f.daily_text("23.10.2026", e=None)
    message_id = await tg.group(501, text)
    assert len(tg.session.of(SetMessageReaction)) == 3
    assert len(tg.session.of(SendMessage)) == 1
    calls = len(tg.session.calls)
    await tg.group(501, text, message_id=message_id)
    assert len(tg.session.calls) == calls


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


async def test_today_has_summary_button_and_private_chat_is_registered(tg: Telegram, maker) -> None:
    await tg.private(501, "/today")
    response = tg.session.of(SendMessage)[-1]
    assert response.parse_mode == "HTML"
    buttons = [button for row in response.reply_markup.inline_keyboard for button in row]
    summary = ReportCb(view="summary", day="20261026").pack()
    assert any(button.callback_data == summary for button in buttons)
    await tg.press(501, summary)
    assert "Итоги дня" in tg.session.texts()[-1]
    async with maker() as session:
        from teamtime.db.models import TelegramIdentity

        identity = await session.scalar(
            select(TelegramIdentity).where(TelegramIdentity.telegram_user_id == 501)
        )
        assert identity.dm_chat_id == 501


@pytest.mark.parametrize(
    "action",
    [
        "/today",
        "/day",
        "/people",
        "/week",
        "/me",
        "/who",
        "week",
        "month",
        "today",
        "summary",
        "people",
    ],
)
async def test_reports_have_no_dashboard_links(tg: Telegram, action: str) -> None:
    if action.startswith("/"):
        await tg.private(501, action)
    else:
        await tg.press(501, MenuCb(action=action).pack())
    messages = tg.session.of(SendMessage)
    assert messages
    for message in messages:
        assert "dashboard.example" not in message.text
        assert "Открыть мой профиль" not in message.text
        if message.reply_markup:
            for row in message.reply_markup.inline_keyboard:
                assert all(button.url is None for button in row)


async def test_week_keeps_all_tasks_in_telegram_with_page_buttons(tg: Telegram) -> None:
    tasks = [f"Задача {index}: " + "описание " * 18 for index in range(15)]
    tasks.append("&" * 500)
    text = f.schedule_text().replace(
        "- задача один\n- задача два", "\n".join(f"- {task}" for task in tasks)
    )
    await tg.group(501, text, thread=f.SCHEDULE_THREAD)
    tg.session.calls.clear()
    await tg.private(501, "/week")
    messages = tg.session.of(SendMessage)
    assert len(messages) == 1
    pages = [messages[0]]
    while True:
        next_page = next(
            (
                button
                for row in pages[-1].reply_markup.inline_keyboard
                for button in row
                if button.text == "Страница ›"
            ),
            None,
        )
        if next_page is None:
            break
        await tg.press(501, next_page.callback_data)
        pages.append(tg.session.of(EditMessageText)[-1])
    assert len(pages) > 1
    assert len(tg.session.of(SendMessage)) == 1
    report = "\n".join(message.text for message in pages)
    assert all(f"Задача {index}:" in report for index in range(15))
    assert "&amp;" * 500 in report
    assert "на сайте" not in report
    assert all("Иванов И.И." in message.text for message in pages)
    assert all(len(message.text.encode("utf-16-le")) // 2 <= 4096 for message in pages)


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
    reply = tg.session.texts()[-1]
    assert "на отпуск" in reply
    assert "<b>02.11.2026</b> по <b>06.11.2026</b> включительно" in reply
    assert "Ждёт решения администратора" in reply
    async with maker() as s:
        assert list(await s.scalars(select(DayStatus))) == []
        requests = list(await s.scalars(select(StatusRequest).order_by(StatusRequest.id)))
        assert len(requests) == 2
        for request in requests:
            await status_requests.decide(s, request.id, True, "admin")
        await s.commit()
        statuses = list(await s.scalars(select(DayStatus).where(DayStatus.retracted_at.is_(None))))
    kinds = {(st.date, st.kind) for st in statuses}
    assert (date(2026, 10, 26), StatusKind.ABSENT) in kinds
    assert len(statuses) == 6


async def test_daily_wizard_preview_and_save_survive_fsm_restart_without_duplicates(
    tg: Telegram, maker
):
    await tg.private(501, "/daily")
    await tg.press(501, PersonalCb(action="draft_day", value="20261023").pack())
    await tg.private(501, "10:00 - 14:00; 15:00 - 18:00")
    await tg.press(501, PersonalCb(action="draft_eff", value="80").pack())
    async with maker() as session:
        draft = await session.scalar(select(BotDraft))
        assert draft is not None and draft.submitted_at is None
        assert await current_dailies(session, date(2026, 10, 23), date(2026, 10, 23)) == []
        draft_id = draft.id
    tg.dp.fsm.storage = MemoryStorage()
    await tg.press(501, PersonalCb(action="draft_save", value=draft_id).pack())
    await tg.press(501, PersonalCb(action="draft_save", value=draft_id).pack())
    async with maker() as session:
        rows = await current_dailies(session, date(2026, 10, 23), date(2026, 10, 23))
        assert len(rows) == 1 and rows[0].version == 1
        assert rows[0].efficiency == 80 and len(rows[0].intervals) == 2
        assert rows[0].tasks == []


async def test_daily_cancel_and_commands_are_available_during_input(tg: Telegram, maker):
    await tg.private(501, "/daily")
    await tg.private(501, "/cancel")
    assert tg.session.texts()[-1] == "Действие отменено."
    await tg.private(501, "/daily")
    await tg.private(501, "23.10.2026")
    await tg.private(501, "25:00 - 28:00")
    assert "Не понял время" in tg.session.texts()[-1]
    await tg.private(501, "/notifications")
    assert "Личные уведомления" in tg.session.texts()[-1]
    async with maker() as session:
        assert await session.scalar(select(BotDraft)) is None


async def test_hours_wizard_preserves_existing_report_text(tg: Telegram, maker):
    await tg.group(501, f.daily_text("23.10.2026"))
    await tg.private(501, "/daily")
    for value in ("23.10.2026", "11:00 - 19:00", "90"):
        await tg.private(501, value)
    async with maker() as session:
        draft_id = (await session.scalar(select(BotDraft))).id
    await tg.press(501, PersonalCb(action="draft_save", value=draft_id).pack())
    async with maker() as session:
        rows = await current_dailies(session, date(2026, 10, 23), date(2026, 10, 23))
        assert rows[0].efficiency == 90
        assert [task.text for task in rows[0].tasks] == ["сделал что-то"]


async def test_daily_wizard_does_not_overwrite_a_newer_report(tg: Telegram, maker):
    await tg.private(501, "/daily")
    for text in ("23.10.2026", "10:00 - 18:00", "80"):
        await tg.private(501, text)
    async with maker() as session:
        draft_id = (await session.scalar(select(BotDraft))).id
    await tg.group(501, f.daily_text("23.10.2026", "11:00 - 19:00", 90))
    await tg.press(501, PersonalCb(action="draft_save", value=draft_id).pack())
    async with maker() as session:
        rows = await current_dailies(session, date(2026, 10, 23), date(2026, 10, 23))
        assert rows[0].efficiency == 90 and rows[0].source.value == "telegram"
        assert (await session.get(BotDraft, draft_id)).submitted_at is None


async def test_personal_notification_preferences_are_saved(tg: Telegram, maker):
    await tg.private(501, "/notifications")
    await tg.press(501, PersonalCb(action="notify_delay", value="30").pack())
    await tg.press(501, PersonalCb(action="notify_quiet").pack())
    await tg.private(501, "22:00–09:00")
    await tg.press(501, PersonalCb(action="notify_toggle").pack())
    async with maker() as session:
        preference = await session.get(NotificationPreference, 1)
        assert not preference.enabled and preference.delay_minutes == 30
        assert preference.quiet_start == 22 * 60 and preference.quiet_end == 9 * 60


async def test_edit_waits_for_old_reaction_retry_and_removes_old_warning(
    tg: Telegram, maker, monkeypatch
):
    entered, release = asyncio.Event(), asyncio.Event()
    request = tg.session.make_request
    first = True

    async def delayed(bot, method, timeout=None):  # noqa: ASYNC109 — сигнатура BaseSession
        nonlocal first
        if isinstance(method, SetMessageReaction) and first:
            first = False
            entered.set()
            await release.wait()
            raise ProxyTimeoutError("Вымышленный сбой прокси")
        return await request(bot, method, timeout)

    monkeypatch.setattr(tg.session, "make_request", delayed)
    monkeypatch.setattr("teamtime.bot.reactions.sleep", AsyncMock())
    original = asyncio.create_task(tg.group(501, f.daily_text(e=None), message_id=800))
    await asyncio.wait_for(entered.wait(), 5)
    edited = asyncio.create_task(tg.group(501, f.daily_text(e=80), message_id=800, edit=True))
    try:
        await asyncio.sleep(0.03)
        assert not edited.done()
    finally:
        release.set()
    await asyncio.gather(original, edited)
    assert reactions(tg) == ["🤔", "✍"]
    warning = tg.session.of(SendMessage)[0]
    assert any(call.chat_id == warning.chat_id for call in tg.session.of(DeleteMessage))
    async with maker() as session:
        raw = await session.scalar(select(RawMessage))
        assert raw.bot_reply_message_id is None


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


async def test_telemetry_does_not_block_other_users_while_reply_is_pending(
    tg: Telegram, maker, monkeypatch
):
    from teamtime.services import diagnostics

    async with maker() as session:
        await diagnostics.set_service(session, "bot", "running", success=True)
        await session.commit()
    entered, release = asyncio.Event(), asyncio.Event()
    original_request = tg.session.make_request
    first = True

    async def delayed(bot, method, timeout=None):  # noqa: ASYNC109 — сигнатура BaseSession
        nonlocal first
        if isinstance(method, SendMessage) and first:
            first = False
            entered.set()
            await release.wait()
        return await original_request(bot, method, timeout)

    monkeypatch.setattr(tg.session, "make_request", delayed)
    pending = asyncio.create_task(tg.private(501, "/help"))
    await asyncio.wait_for(entered.wait(), 5)
    try:
        await asyncio.wait_for(tg.private(503, "/help"), 3)
        assert not pending.done()
    finally:
        release.set()
        await pending
