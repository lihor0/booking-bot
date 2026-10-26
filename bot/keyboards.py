from datetime import date, datetime

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

from bot.config import Service
from bot.db import Booking
from bot.texts import fmt_day_short, fmt_dt, fmt_price

BTN_BOOK = "📅 Записаться"
BTN_MY = "📋 Мои записи"
BTN_PRICES = "💈 Услуги и цены"
BTN_CONTACTS = "📍 Контакты"
BTN_CANCEL = "❌ Отмена"


class ServiceCb(CallbackData, prefix="svc"):
    id: str


class DayCb(CallbackData, prefix="day"):
    day: str  # YYYY-MM-DD


class TimeCb(CallbackData, prefix="tm"):
    hm: str  # HHMM


class BackCb(CallbackData, prefix="back"):
    to: str  # services | days


class ConfirmCb(CallbackData, prefix="cf"):
    ok: bool


class CancelCb(CallbackData, prefix="cn"):
    id: int
    sure: bool = False


class AdminListCb(CallbackData, prefix="al"):
    period: str  # today | tomorrow | upcoming


class AdminCancelCb(CallbackData, prefix="ac"):
    id: int
    sure: bool = False


def main_menu() -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardBuilder()
    for text in (BTN_BOOK, BTN_MY, BTN_PRICES, BTN_CONTACTS):
        kb.button(text=text)
    kb.adjust(1, 1, 2)
    return kb.as_markup(resize_keyboard=True)


def services_kb(services: tuple[Service, ...]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for s in services:
        kb.button(text=f"{s.name} — {fmt_price(s.price)}", callback_data=ServiceCb(id=s.id))
    kb.adjust(1)
    return kb.as_markup()


def days_kb(days: list[date]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for d in days:
        kb.button(text=fmt_day_short(d), callback_data=DayCb(day=d.isoformat()))
    kb.button(text="« К услугам", callback_data=BackCb(to="services"))
    kb.adjust(*([3] * (len(days) // 3)), *([len(days) % 3] if len(days) % 3 else []), 1)
    return kb.as_markup()


def slots_kb(slots: list[datetime]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for t in slots:
        kb.button(text=f"{t:%H:%M}", callback_data=TimeCb(hm=f"{t:%H%M}"))
    kb.button(text="« К датам", callback_data=BackCb(to="days"))
    kb.adjust(*([4] * (len(slots) // 4)), *([len(slots) % 4] if len(slots) % 4 else []), 1)
    return kb.as_markup()


def text_input_kb(suggestion: str | None = None, request_contact: bool = False) -> ReplyKeyboardMarkup:
    rows = []
    if request_contact:
        rows.append([KeyboardButton(text="📱 Отправить мой номер", request_contact=True)])
    if suggestion:
        rows.append([KeyboardButton(text=suggestion)])
    rows.append([KeyboardButton(text=BTN_CANCEL)])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True, one_time_keyboard=True)


def confirm_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Подтвердить", callback_data=ConfirmCb(ok=True))
    kb.button(text="✖️ Отменить", callback_data=ConfirmCb(ok=False))
    return kb.as_markup()


def my_bookings_kb(bookings: list[Booking]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for b in bookings:
        kb.button(text=f"Отменить: {fmt_dt(b.start)}", callback_data=CancelCb(id=b.id))
    kb.adjust(1)
    return kb.as_markup()


def sure_kb(cb_class: type[CancelCb] | type[AdminCancelCb], booking_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="Да, отменить", callback_data=cb_class(id=booking_id, sure=True))
    return kb.as_markup()


def admin_menu() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="Сегодня", callback_data=AdminListCb(period="today"))
    kb.button(text="Завтра", callback_data=AdminListCb(period="tomorrow"))
    kb.button(text="Все предстоящие", callback_data=AdminListCb(period="upcoming"))
    kb.adjust(2, 1)
    return kb.as_markup()


def admin_booking_kb(booking_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="Отменить запись", callback_data=AdminCancelCb(id=booking_id))
    return kb.as_markup()
