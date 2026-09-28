"""The Bot's own profile photo, fetched for its account in the role's list."""

from __future__ import annotations

import logging

from telegram import Bot
from telegram.error import TelegramError

from core.accounts import avatar_data_uri

logger = logging.getLogger("plugins.telegram.channel")


async def fetch_bot_avatar(bot: Bot, bot_id: int) -> str | None:
    """The Bot's current profile photo as a data URI.

    Returns "" when the Bot has no photo and None when it cannot be fetched;
    a network boundary, so failures are logged and never raised.
    """
    try:
        photos = await bot.get_user_profile_photos(bot_id, limit=1)
        if not photos.photos:
            return ""
        # Sizes are ordered smallest first; the thumbnail suits an avatar.
        smallest = photos.photos[0][0]
        file = await bot.get_file(smallest.file_id)
        return avatar_data_uri(bytes(await file.download_as_bytearray()))
    except (TelegramError, ValueError) as exc:
        logger.warning("Telegram Bot %s 头像获取失败: %s", bot_id, exc)
        return None
