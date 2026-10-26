import logging

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

from bot.config import Config

log = logging.getLogger(__name__)


async def safe_send(bot: Bot, chat_id: int, text: str) -> bool:
    """Отправка, которая не роняет обработчик, если пользователь заблокировал бота."""
    try:
        await bot.send_message(chat_id, text)
        return True
    except TelegramAPIError as e:
        log.warning("Не удалось отправить сообщение %s: %s", chat_id, e)
        return False


async def notify_admins(bot: Bot, cfg: Config, text: str) -> None:
    for admin_id in cfg.admin_ids:
        await safe_send(bot, admin_id, text)
