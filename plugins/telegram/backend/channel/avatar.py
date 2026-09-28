"""The Bot's own profile photo, fetched for its account in the role's list."""

from __future__ import annotations

import base64
import logging

from telegram import Bot
from telegram.error import TelegramError

logger = logging.getLogger("plugins.telegram.channel")

# The host refuses larger avatars; the smallest photo size is a few KiB.
_MAX_AVATAR_BYTES = 256 * 1024


def _avatar_data_uri(content: bytes) -> str:
    """The downloaded photo as the ``data:`` URI the host accepts."""
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        mime = "image/png"
    elif content.startswith(b"\xff\xd8\xff"):
        mime = "image/jpeg"
    elif content.startswith((b"GIF87a", b"GIF89a")):
        mime = "image/gif"
    elif content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        mime = "image/webp"
    else:
        raise ValueError("Telegram 头像不是 PNG、JPEG、GIF 或 WebP 图片")
    if len(content) > _MAX_AVATAR_BYTES:
        raise ValueError("Telegram 头像超过 256 KiB")
    return f"data:{mime};base64,{base64.b64encode(content).decode('ascii')}"


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
        return _avatar_data_uri(bytes(await file.download_as_bytearray()))
    except (TelegramError, ValueError) as exc:
        logger.warning("Telegram Bot %s 头像获取失败: %s", bot_id, exc)
        return None
