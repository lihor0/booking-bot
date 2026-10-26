import asyncio
import logging
from datetime import timedelta

from aiogram import Bot

from bot import texts
from bot.config import Config
from bot.db import Database
from bot.notify import safe_send

log = logging.getLogger(__name__)

CHECK_INTERVAL = 60  # секунд


async def send_due_reminders(bot: Bot, db: Database, cfg: Config) -> int:
    now = cfg.now()
    due = await db.due_reminders(now, now + timedelta(minutes=cfg.remind_before))
    for booking in due:
        await safe_send(bot, booking.user_id, texts.reminder(booking, cfg))
        await db.mark_reminded(booking.id)
    return len(due)


async def reminder_loop(bot: Bot, db: Database, cfg: Config) -> None:
    while True:
        try:
            sent = await send_due_reminders(bot, db, cfg)
            if sent:
                log.info("Отправлено напоминаний: %d", sent)
        except Exception:
            log.exception("Ошибка в цикле напоминаний")
        await asyncio.sleep(CHECK_INTERVAL)
