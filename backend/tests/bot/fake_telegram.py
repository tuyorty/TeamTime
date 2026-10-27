"""Поддельный Telegram: перехватывает вызовы Bot API и возвращает правдоподобные ответы.

Хендлеры, диспетчер и база настоящие — подменяется только сеть.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from itertools import count
from typing import Any

from aiogram import Bot
from aiogram.client.session.base import BaseSession
from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import (
    AnswerCallbackQuery,
    DeleteMessage,
    EditMessageReplyMarkup,
    EditMessageText,
    GetChatMember,
    GetMe,
    SendMessage,
    SetMessageReaction,
    TelegramMethod,
)
from aiogram.types import (
    CallbackQuery,
    Chat,
    ChatMemberAdministrator,
    ChatMemberMember,
    Message,
    RichMessage,
    Update,
    User,
)

from teamtime.core import clock

BOT_USER = User(id=42, is_bot=True, first_name="xTime", username="teamtime_test_bot")
GROUP = Chat(id=-1001234567890, type="supergroup", title="Вымышленная команда", is_forum=True)
# Чужая группа: кто-то добавил туда бота, админ её не разрешал.
STRANGERS = Chat(id=-1009999999999, type="supergroup", title="Чужая группа", is_forum=True)


class FakeSession(BaseSession):
    def __init__(self) -> None:
        super().__init__()
        self.calls: list[TelegramMethod[Any]] = []
        self.fail_reactions = False
        self.admins: set[int] = set()
        self._ids = count(10_000)

    async def close(self) -> None:
        return None

    async def stream_content(self, *args: Any, **kwargs: Any) -> AsyncGenerator[bytes, None]:
        yield b""

    def of(self, kind: type) -> list[Any]:
        return [c for c in self.calls if isinstance(c, kind)]

    def texts(self) -> list[str]:
        return [c.text for c in self.calls if isinstance(c, SendMessage | EditMessageText)]

    async def make_request(
        self,
        bot: Bot,
        method: TelegramMethod[Any],
        timeout: int | None = None,  # noqa: ASYNC109 — сигнатура BaseSession
    ) -> Any:
        self.calls.append(method)
        if isinstance(method, GetMe):
            return BOT_USER
        if isinstance(method, SetMessageReaction):
            if self.fail_reactions:
                raise TelegramBadRequest(method=method, message="Bad Request: REACTION_INVALID")
            return True
        if isinstance(method, SendMessage):
            chat_type = "private" if int(method.chat_id) > 0 else "supergroup"
            return Message(
                message_id=next(self._ids),
                date=clock.now(),
                chat=Chat(id=int(method.chat_id), type=chat_type),
                text=method.text,
            )
        if isinstance(method, GetChatMember):
            if method.user_id in self.admins:
                # Хендлеру нужен только статус; остальные права Bot API здесь не важны.
                return ChatMemberAdministrator.model_construct(
                    status="administrator",
                    user=User(id=method.user_id, is_bot=False, first_name="Админ"),
                )
            return ChatMemberMember(user=User(id=method.user_id, is_bot=False, first_name="X"))
        if isinstance(method, DeleteMessage | AnswerCallbackQuery | EditMessageReplyMarkup):
            return True
        if isinstance(method, EditMessageText):
            return True
        return True


class Telegram:
    """Помощник для сценариев: строит апдейты и скармливает их диспетчеру."""

    def __init__(self, dp: Any, bot: Bot, session: FakeSession) -> None:
        self.dp, self.bot, self.session = dp, bot, session
        self._update_ids = count(1)
        self._message_ids = count(1)

    def user(self, uid: int, name: str = "Вымышленный") -> User:
        return User(id=uid, is_bot=False, first_name=name, username=f"user{uid}")

    async def group(
        self,
        uid: int,
        text: str,
        *,
        thread: int | None = 22,
        message_id: int | None = None,
        edit: bool = False,
        chat: Chat = GROUP,
        name: str = "Вымышленный",
        rich: dict[str, Any] | None = None,
    ) -> int:
        """``rich`` — «богатое» сообщение (rich_message) вместо обычного текста."""
        mid = message_id or next(self._message_ids)
        msg = Message(
            message_id=mid,
            date=datetime(2026, 10, 26, 6, 0, tzinfo=UTC),
            chat=chat,
            from_user=self.user(uid, name),
            text=None if rich else text,
            rich_message=RichMessage.model_validate(rich) if rich else None,
            message_thread_id=thread,
            is_topic_message=thread is not None,
            edit_date=int(datetime(2026, 10, 26, 6, 30, tzinfo=UTC).timestamp()) if edit else None,
        )
        update = Update(
            update_id=next(self._update_ids),
            **({"edited_message": msg} if edit else {"message": msg}),
        )
        await self.dp.feed_update(self.bot, update)
        return mid

    async def private(self, uid: int, text: str) -> None:
        msg = Message(
            message_id=next(self._message_ids),
            date=datetime(2026, 10, 26, 7, 0, tzinfo=UTC),
            chat=Chat(id=uid, type="private"),
            from_user=self.user(uid),
            text=text,
        )
        await self.dp.feed_update(self.bot, Update(update_id=next(self._update_ids), message=msg))

    async def press(self, uid: int, data: str) -> None:
        query = CallbackQuery(
            id=str(next(self._update_ids)),
            from_user=self.user(uid),
            chat_instance="x",
            data=data,
            message=Message(
                message_id=next(self._message_ids),
                date=clock.now(),
                chat=Chat(id=uid, type="private"),
                text="меню",
            ),
        )
        await self.dp.feed_update(
            self.bot, Update(update_id=next(self._update_ids), callback_query=query)
        )
