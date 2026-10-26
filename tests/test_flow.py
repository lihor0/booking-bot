"""Сквозной сценарий: клиент записывается через бота, админ получает уведомление.

Telegram API подменён сессией, которая записывает все запросы бота вместо отправки в сеть.
"""
from datetime import datetime
from itertools import count

import pytest
from aiogram import Bot, Dispatcher
from aiogram.client.session.base import BaseSession
from aiogram.methods import EditMessageText, SendMessage, TelegramMethod
from aiogram.types import CallbackQuery, Chat, Contact, Message, Update, User

from bot.handlers import admin, client

USER = User(id=1, is_bot=False, first_name="Иван")
CHAT = Chat(id=1, type="private")
_ids = count(1)


class RecordingSession(BaseSession):
    def __init__(self):
        super().__init__()
        self.requests: list[TelegramMethod] = []

    async def make_request(self, bot, method, timeout=None):
        self.requests.append(method)
        if isinstance(method, SendMessage):
            return Message(
                message_id=next(_ids), date=datetime.now(), text=method.text,
                chat=Chat(id=method.chat_id, type="private"),
            )
        return True

    async def stream_content(self, *args, **kwargs):  # pragma: no cover
        raise NotImplementedError

    async def close(self):
        pass

    def sent(self, chat_id: int | None = None) -> list[SendMessage | EditMessageText]:
        return [
            r for r in self.requests
            if isinstance(r, (SendMessage, EditMessageText)) and (chat_id is None or getattr(r, "chat_id", None) == chat_id)
        ]

    def last_buttons(self) -> list[str]:
        """callback_data всех inline-кнопок из последнего сообщения с inline-клавиатурой."""
        for r in reversed(self.sent()):
            markup = r.reply_markup
            if markup is not None and hasattr(markup, "inline_keyboard"):
                return [b.callback_data for row in markup.inline_keyboard for b in row]
        raise AssertionError("нет inline-клавиатуры")


@pytest.fixture
async def env(cfg, db):
    session = RecordingSession()
    bot = Bot("42:TEST", session=session)
    dp = Dispatcher()
    dp["cfg"], dp["db"] = cfg, db
    dp.include_routers(admin.router, client.router)
    yield bot, dp, session
    # Роутеры — модульные синглтоны, отвязываем их для следующего теста
    dp.sub_routers.clear()
    admin.router._parent_router = None
    client.router._parent_router = None


def text_update(text: str) -> Update:
    return Update(update_id=next(_ids), message=Message(
        message_id=next(_ids), date=datetime.now(), chat=CHAT, from_user=USER, text=text,
    ))


def contact_update(phone: str) -> Update:
    return Update(update_id=next(_ids), message=Message(
        message_id=next(_ids), date=datetime.now(), chat=CHAT, from_user=USER,
        contact=Contact(phone_number=phone, first_name="Иван"),
    ))


def callback_update(data: str) -> Update:
    msg = Message(message_id=next(_ids), date=datetime.now(), chat=CHAT, text="...")
    return Update(update_id=next(_ids), callback_query=CallbackQuery(
        id=str(next(_ids)), from_user=USER, chat_instance="x", message=msg, data=data,
    ))


async def feed(bot, dp, update):
    # Так же, как aiogram при получении апдейта из сети: все вложенные объекты привязываются к боту
    bound = Update.model_validate(update.model_dump(exclude_none=True), context={"bot": bot})
    await dp.feed_update(bot, bound)


async def test_full_booking_flow(env, db, cfg):
    bot, dp, session = env

    await feed(bot, dp, text_update("/start"))
    assert "Тестовый салон" in session.sent()[-1].text

    await feed(bot, dp, text_update("📅 Записаться"))
    await feed(bot, dp, callback_update("svc:haircut"))

    days = [d for d in session.last_buttons() if d.startswith("day:")]
    assert days, "должны быть свободные даты"
    await feed(bot, dp, callback_update(days[-1]))

    times = [t for t in session.last_buttons() if t.startswith("tm:")]
    await feed(bot, dp, callback_update(times[0]))
    assert "Как к вам обращаться" in session.sent()[-1].text

    # Кнопка меню посреди ввода не должна стать именем
    await feed(bot, dp, text_update("💈 Услуги и цены"))
    assert "Услуги и цены" in session.sent()[-1].text

    await feed(bot, dp, text_update("Иван"))
    await feed(bot, dp, contact_update("79001234567"))
    assert "Проверьте запись" in session.sent()[-1].text

    await feed(bot, dp, callback_update("cf:1"))
    assert "Вы записаны" in session.sent(chat_id=CHAT.id)[-1].text

    bookings = await db.upcoming(cfg.now(), user_id=USER.id)
    assert len(bookings) == 1
    assert bookings[0].phone == "+79001234567"
    assert bookings[0].client_name == "Иван"

    admin_msgs = session.sent(chat_id=999)
    assert admin_msgs and "Новая запись" in admin_msgs[-1].text

    # Клиент отменяет запись
    await feed(bot, dp, text_update("📋 Мои записи"))
    await feed(bot, dp, callback_update(f"cn:{bookings[0].id}:0"))
    await feed(bot, dp, callback_update(f"cn:{bookings[0].id}:1"))
    assert await db.upcoming(cfg.now(), user_id=USER.id) == []
    assert "отменил" in session.sent(chat_id=999)[-1].text


async def test_non_admin_cannot_use_admin_commands(env):
    bot, dp, session = env
    await feed(bot, dp, text_update("/admin"))
    assert not any("Панель администратора" in (r.text or "") for r in session.sent())
