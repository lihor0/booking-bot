import re
from datetime import date, datetime, timedelta
from html import escape

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from bot import keyboards as kb
from bot import texts
from bot.config import Config, Service
from bot.db import Database, SlotTaken
from bot.notify import notify_admins
from bot.slots import candidate_days, free_slots

router = Router(name="client")

PHONE_RE = re.compile(r"^\+?\d{10,15}$")
# Нажатие кнопки меню посреди ввода не должно приниматься за имя или телефон
USER_INPUT = F.text & ~F.text.in_({kb.BTN_BOOK, kb.BTN_MY, kb.BTN_PRICES, kb.BTN_CONTACTS, kb.BTN_CANCEL})


class BookingForm(StatesGroup):
    service = State()
    day = State()
    time = State()
    name = State()
    phone = State()
    confirm = State()


# --- главное меню ---

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, cfg: Config):
    await state.clear()
    await message.answer(texts.greeting(cfg, message.from_user.first_name), reply_markup=kb.main_menu())


@router.message(F.text == kb.BTN_PRICES)
async def show_prices(message: Message, cfg: Config):
    await message.answer(texts.price_list(cfg))


@router.message(F.text == kb.BTN_CONTACTS)
async def show_contacts(message: Message, cfg: Config):
    await message.answer(texts.contacts(cfg))


@router.message(F.text == kb.BTN_CANCEL)
async def cancel_input(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Запись отменена.", reply_markup=kb.main_menu())


# --- запись: услуга → дата → время → имя → телефон → подтверждение ---

@router.message(F.text == kb.BTN_BOOK)
@router.message(Command("book"))
async def start_booking(message: Message, state: FSMContext, cfg: Config):
    await state.clear()
    await state.set_state(BookingForm.service)
    await message.answer("Выберите услугу:", reply_markup=kb.services_kb(cfg.services))


async def _available_days(db: Database, cfg: Config, service: Service) -> list[date]:
    now = cfg.now()
    days = []
    for day in candidate_days(now, cfg, await db.blocked_days()):
        if free_slots(day, service.duration, await db.busy_intervals(day), now, cfg):
            days.append(day)
    return days


async def _show_days(cb: CallbackQuery, state: FSMContext, cfg: Config, db: Database, service: Service):
    days = await _available_days(db, cfg, service)
    await state.set_state(BookingForm.day)
    text = f"<b>{texts.service_line(service)}</b>\n\n"
    text += "Выберите дату:" if days else "К сожалению, свободных дат пока нет. Попробуйте выбрать другую услугу."
    await cb.message.edit_text(text, reply_markup=kb.days_kb(days))


async def _show_slots(cb: CallbackQuery, state: FSMContext, cfg: Config, db: Database, service: Service, day: date):
    slots = free_slots(day, service.duration, await db.busy_intervals(day), cfg.now(), cfg)
    await state.set_state(BookingForm.time)
    text = f"<b>{texts.service_line(service)}</b>\n{texts.fmt_day(day)}\n\n"
    text += "Выберите время:" if slots else "На этот день всё занято, выберите другую дату."
    await cb.message.edit_text(text, reply_markup=kb.slots_kb(slots))


async def _service_from_state(state: FSMContext, cfg: Config) -> Service | None:
    data = await state.get_data()
    return cfg.service(data.get("service_id", ""))


@router.callback_query(BookingForm.service, kb.ServiceCb.filter())
async def pick_service(cb: CallbackQuery, callback_data: kb.ServiceCb, state: FSMContext, cfg: Config, db: Database):
    service = cfg.service(callback_data.id)
    if service is None:
        await cb.answer("Услуга больше недоступна", show_alert=True)
        return
    await state.update_data(service_id=service.id)
    await _show_days(cb, state, cfg, db, service)
    await cb.answer()


@router.callback_query(BookingForm.day, kb.DayCb.filter())
async def pick_day(cb: CallbackQuery, callback_data: kb.DayCb, state: FSMContext, cfg: Config, db: Database):
    service = await _service_from_state(state, cfg)
    if service is None:
        await cb.answer("Начните запись заново", show_alert=True)
        return
    day = date.fromisoformat(callback_data.day)
    await state.update_data(day=day.isoformat())
    await _show_slots(cb, state, cfg, db, service, day)
    await cb.answer()


@router.callback_query(BookingForm.time, kb.TimeCb.filter())
async def pick_time(cb: CallbackQuery, callback_data: kb.TimeCb, state: FSMContext, cfg: Config, db: Database):
    data = await state.get_data()
    service = cfg.service(data.get("service_id", ""))
    if service is None or "day" not in data:
        await cb.answer("Начните запись заново", show_alert=True)
        return
    day = date.fromisoformat(data["day"])
    start = datetime.strptime(f"{data['day']} {callback_data.hm}", "%Y-%m-%d %H%M")

    # Клавиатура могла устареть, пока клиент думал
    if start not in free_slots(day, service.duration, await db.busy_intervals(day), cfg.now(), cfg):
        await cb.answer("Это время уже занято, выберите другое", show_alert=True)
        await _show_slots(cb, state, cfg, db, service, day)
        return

    await state.update_data(start=start.isoformat())
    await cb.message.edit_text(f"<b>{texts.service_line(service)}</b>\n🗓 {texts.fmt_dt(start)}")
    await cb.answer()

    last = await db.last_contact(cb.from_user.id)
    if last:
        await state.update_data(last_phone=last[1])
    await state.set_state(BookingForm.name)
    await cb.message.answer(
        "Как к вам обращаться?", reply_markup=kb.text_input_kb(suggestion=last[0] if last else None)
    )


@router.callback_query(kb.BackCb.filter())
async def go_back(cb: CallbackQuery, callback_data: kb.BackCb, state: FSMContext, cfg: Config, db: Database):
    service = await _service_from_state(state, cfg)
    if callback_data.to == "days" and service is not None:
        await _show_days(cb, state, cfg, db, service)
    else:
        await state.set_state(BookingForm.service)
        await cb.message.edit_text("Выберите услугу:", reply_markup=kb.services_kb(cfg.services))
    await cb.answer()


@router.message(BookingForm.name, USER_INPUT)
async def enter_name(message: Message, state: FSMContext):
    name = message.text.strip()
    if not 2 <= len(name) <= 50:
        await message.answer("Введите имя длиной от 2 до 50 символов.")
        return
    await state.update_data(name=name)
    await state.set_state(BookingForm.phone)
    data = await state.get_data()
    await message.answer(
        "Оставьте номер телефона — нажмите кнопку ниже или введите вручную (например, +79001234567).",
        reply_markup=kb.text_input_kb(suggestion=data.get("last_phone"), request_contact=True),
    )


def normalize_phone(raw: str) -> str | None:
    digits = re.sub(r"[\s\-()]", "", raw)
    if digits.startswith("8") and len(digits) == 11:
        digits = "+7" + digits[1:]
    elif digits.isdigit():
        digits = "+" + digits
    return digits if PHONE_RE.match(digits) else None


@router.message(BookingForm.phone, F.contact | USER_INPUT)
async def enter_phone(message: Message, state: FSMContext, cfg: Config):
    raw = message.contact.phone_number if message.contact else message.text
    phone = normalize_phone(raw)
    if phone is None:
        await message.answer("Не похоже на номер телефона. Попробуйте ещё раз, например +79001234567.")
        return
    await state.update_data(phone=phone)
    await state.set_state(BookingForm.confirm)

    data = await state.get_data()
    service = cfg.service(data["service_id"])
    start = datetime.fromisoformat(data["start"])
    await message.answer("Почти готово!", reply_markup=kb.main_menu())
    await message.answer(
        "<b>Проверьте запись:</b>\n\n"
        f"✂️ {texts.service_line(service)}\n"
        f"🗓 {texts.fmt_dt(start)}\n"
        f"👤 {escape(data['name'])}, {phone}",
        reply_markup=kb.confirm_kb(),
    )


@router.callback_query(BookingForm.confirm, kb.ConfirmCb.filter())
async def confirm(cb: CallbackQuery, callback_data: kb.ConfirmCb, state: FSMContext, cfg: Config, db: Database, bot: Bot):
    data = await state.get_data()
    if not callback_data.ok:
        await state.clear()
        await cb.message.edit_text("Запись отменена. Можно начать заново через «📅 Записаться».")
        await cb.answer()
        return

    service = cfg.service(data["service_id"])
    start = datetime.fromisoformat(data["start"])
    now = cfg.now()
    try:
        booking = await db.create_booking(
            user_id=cb.from_user.id,
            client_name=data["name"],
            phone=data["phone"],
            service_id=service.id,
            start=start,
            end=start + timedelta(minutes=service.duration),
            # Если до визита меньше окна напоминания — отдельное напоминание не нужно
            reminded=start - now <= timedelta(minutes=cfg.remind_before),
        )
    except SlotTaken:
        await cb.answer("Пока вы оформляли запись, это время заняли 😔", show_alert=True)
        await _show_slots(cb, state, cfg, db, service, start.date())
        return

    await state.clear()
    await cb.message.edit_text(
        "✅ <b>Вы записаны!</b>\n\n"
        f"{texts.booking_card(booking, cfg)}\n\n"
        f"📍 {escape(cfg.address)}\n"
        f"Мы напомним о визите за {texts.fmt_duration(cfg.remind_before)}."
    )
    await cb.answer()
    await notify_admins(bot, cfg, "🆕 <b>Новая запись</b>\n\n" + texts.booking_card(booking, cfg, for_admin=True))


# --- мои записи ---

@router.message(F.text == kb.BTN_MY)
@router.message(Command("my"))
async def my_bookings(message: Message, state: FSMContext, cfg: Config, db: Database):
    await state.clear()
    bookings = await db.upcoming(cfg.now(), user_id=message.from_user.id)
    if not bookings:
        await message.answer("У вас нет предстоящих записей.", reply_markup=kb.main_menu())
        return
    cards = "\n\n".join(texts.booking_card(b, cfg) for b in bookings)
    await message.answer(f"<b>Ваши записи:</b>\n\n{cards}", reply_markup=kb.my_bookings_kb(bookings))


@router.callback_query(kb.CancelCb.filter())
async def cancel_booking(cb: CallbackQuery, callback_data: kb.CancelCb, cfg: Config, db: Database, bot: Bot):
    booking = await db.get_booking(callback_data.id)
    if booking is None or booking.user_id != cb.from_user.id or booking.status != "active":
        await cb.answer("Запись не найдена или уже отменена", show_alert=True)
        return
    if not callback_data.sure:
        await cb.message.answer(
            f"Отменить запись?\n\n{texts.booking_card(booking, cfg)}",
            reply_markup=kb.sure_kb(kb.CancelCb, booking.id),
        )
        await cb.answer()
        return

    await db.cancel_booking(booking.id)
    await cb.message.edit_text("Запись отменена. Будем рады видеть вас в другой раз!")
    await cb.answer()
    await notify_admins(bot, cfg, "❌ <b>Клиент отменил запись</b>\n\n" + texts.booking_card(booking, cfg, for_admin=True))
