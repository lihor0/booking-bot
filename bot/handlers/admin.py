from datetime import date, datetime, timedelta

from aiogram import Bot, Router
from aiogram.filters import BaseFilter, Command, CommandObject
from aiogram.types import CallbackQuery, Message, TelegramObject

from bot import keyboards as kb
from bot import texts
from bot.config import Config
from bot.db import Database
from bot.notify import safe_send


class IsAdmin(BaseFilter):
    async def __call__(self, event: TelegramObject, cfg: Config) -> bool:
        return event.from_user is not None and event.from_user.id in cfg.admin_ids


router = Router(name="admin")
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())

HELP = (
    "<b>Панель администратора</b>\n\n"
    "/admin — записи на сегодня, завтра и все предстоящие\n"
    "/close 31.12 — закрыть день для записи\n"
    "/open 31.12 — снова открыть день\n"
    "/closed — список закрытых дней"
)


def parse_day(raw: str | None, today: date) -> date | None:
    """Принимает 31.12, 31.12.2026 или 2026-12-31. Без года — ближайшая такая дата в будущем."""
    if not raw:
        return None
    raw = raw.strip()
    for fmt in ("%d.%m.%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            pass
    try:
        parsed = datetime.strptime(f"{raw}.{today.year}", "%d.%m.%Y").date()
    except ValueError:
        return None
    return parsed if parsed >= today else parsed.replace(year=today.year + 1)


@router.message(Command("admin"))
async def cmd_admin(message: Message):
    await message.answer(HELP, reply_markup=kb.admin_menu())


@router.callback_query(kb.AdminListCb.filter())
async def list_bookings(cb: CallbackQuery, callback_data: kb.AdminListCb, cfg: Config, db: Database):
    today = cfg.now().date()
    if callback_data.period == "today":
        title, bookings = f"Сегодня, {texts.fmt_day(today)}", await db.bookings_for_day(today)
    elif callback_data.period == "tomorrow":
        tomorrow = today + timedelta(days=1)
        title, bookings = f"Завтра, {texts.fmt_day(tomorrow)}", await db.bookings_for_day(tomorrow)
    else:
        title, bookings = "Все предстоящие", await db.upcoming(cfg.now())
    await cb.answer()

    if not bookings:
        await cb.message.answer(f"<b>{title}</b>: записей нет.")
        return
    await cb.message.answer(f"<b>{title}</b> — записей: {len(bookings)}")
    for b in bookings:
        await cb.message.answer(texts.booking_card(b, cfg, for_admin=True), reply_markup=kb.admin_booking_kb(b.id))


@router.callback_query(kb.AdminCancelCb.filter())
async def admin_cancel(cb: CallbackQuery, callback_data: kb.AdminCancelCb, cfg: Config, db: Database, bot: Bot):
    booking = await db.get_booking(callback_data.id)
    if booking is None or booking.status != "active":
        await cb.answer("Запись уже отменена", show_alert=True)
        return
    if not callback_data.sure:
        await cb.message.edit_reply_markup(reply_markup=kb.sure_kb(kb.AdminCancelCb, booking.id))
        await cb.answer("Нажмите ещё раз для подтверждения")
        return

    await db.cancel_booking(booking.id)
    await cb.message.edit_text("<s>" + texts.booking_card(booking, cfg, for_admin=True) + "</s>\n\nОтменена ❌")
    await cb.answer("Запись отменена")
    await safe_send(
        bot,
        booking.user_id,
        "😔 <b>Ваша запись отменена администратором</b>\n\n"
        f"{texts.booking_card(booking, cfg)}\n\n"
        "Приносим извинения. Выберите другое время через «📅 Записаться».",
    )


@router.message(Command("close"))
async def cmd_close(message: Message, command: CommandObject, cfg: Config, db: Database):
    day = parse_day(command.args, cfg.now().date())
    if day is None:
        await message.answer("Укажите дату: /close 31.12")
        return
    await db.block_day(day)
    existing = await db.bookings_for_day(day)
    text = f"🔒 {texts.fmt_day(day)} закрыт для новых записей."
    if existing:
        text += f"\n\n⚠️ На этот день уже есть записи ({len(existing)}) — их нужно отменить вручную через /admin."
    await message.answer(text)


@router.message(Command("open"))
async def cmd_open(message: Message, command: CommandObject, cfg: Config, db: Database):
    day = parse_day(command.args, cfg.now().date())
    if day is None:
        await message.answer("Укажите дату: /open 31.12")
        return
    await db.unblock_day(day)
    await message.answer(f"🔓 {texts.fmt_day(day)} снова открыт для записи.")


@router.message(Command("closed"))
async def cmd_closed(message: Message, cfg: Config, db: Database):
    today = cfg.now().date()
    days = sorted(d for d in await db.blocked_days() if d >= today)
    if not days:
        await message.answer("Закрытых дней нет.")
        return
    await message.answer("<b>Закрытые дни:</b>\n" + "\n".join(f"• {texts.fmt_day(d)}" for d in days))
