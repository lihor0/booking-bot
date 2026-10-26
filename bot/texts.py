from datetime import date, datetime
from html import escape

from bot.config import Config, Service
from bot.db import Booking

WEEKDAYS = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]
MONTHS = [
    "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
]


def fmt_day_short(d: date) -> str:
    return f"{WEEKDAYS[d.weekday()]}, {d:%d.%m}"


def fmt_day(d: date) -> str:
    return f"{d.day} {MONTHS[d.month - 1]} ({WEEKDAYS[d.weekday()]})"


def fmt_dt(dt: datetime) -> str:
    return f"{fmt_day(dt.date())} в {dt:%H:%M}"


def fmt_price(price: int) -> str:
    return f"{price:,}".replace(",", " ") + " ₽"


def fmt_duration(minutes: int) -> str:
    hours, mins = divmod(minutes, 60)
    parts = []
    if hours:
        parts.append(f"{hours} ч")
    if mins:
        parts.append(f"{mins} мин")
    return " ".join(parts)


def greeting(cfg: Config, first_name: str | None) -> str:
    name = f", {escape(first_name)}" if first_name else ""
    return (
        f"Здравствуйте{name}! 👋\n\n"
        f"Это бот <b>{escape(cfg.business_name)}</b>. Здесь можно записаться к нам "
        "за пару нажатий, посмотреть или отменить свои записи.\n\n"
        "Выберите действие в меню ниже."
    )


def price_list(cfg: Config) -> str:
    lines = [f"<b>Услуги и цены — {escape(cfg.business_name)}</b>\n"]
    for s in cfg.services:
        lines.append(f"• {escape(s.name)} — <b>{fmt_price(s.price)}</b> ({fmt_duration(s.duration)})")
    return "\n".join(lines)


def contacts(cfg: Config) -> str:
    days = ", ".join(WEEKDAYS[d - 1] for d in sorted(cfg.workdays))
    lines = [f"<b>{escape(cfg.business_name)}</b>"]
    if cfg.address:
        lines.append(f"📍 {escape(cfg.address)}")
    if cfg.phone:
        lines.append(f"📞 {escape(cfg.phone)}")
    lines.append(f"🕒 {days}: {cfg.work_start:%H:%M}–{cfg.work_end:%H:%M}")
    return "\n".join(lines)


def service_line(service: Service) -> str:
    return f"{escape(service.name)} · {fmt_price(service.price)} · {fmt_duration(service.duration)}"


def booking_card(b: Booking, cfg: Config, for_admin: bool = False) -> str:
    service = cfg.service(b.service_id)
    service_name = escape(service.name) if service else b.service_id
    lines = [f"🗓 <b>{fmt_dt(b.start)}</b>–{b.end:%H:%M}", f"✂️ {service_name}"]
    if service:
        lines.append(f"💳 {fmt_price(service.price)}")
    if for_admin:
        lines.append(f"👤 {escape(b.client_name)}, {escape(b.phone)}")
        lines.append(f'<a href="tg://user?id={b.user_id}">написать клиенту</a> · #{b.id}')
    return "\n".join(lines)


def reminder(b: Booking, cfg: Config) -> str:
    return (
        "⏰ <b>Напоминаем о записи</b>\n\n"
        f"{booking_card(b, cfg)}\n\n"
        f"Ждём вас: {escape(cfg.address)}\n"
        "Если планы изменились — отмените запись в разделе «Мои записи»."
    )
