"""Telegram profile photos.

The Bot's own photo becomes a data URI for its account in the role's list; the
photos of message senders and chats go to the host's cache (``ctx.avatars``).
"""

from __future__ import annotations

import base64
import logging
from typing import TYPE_CHECKING

from telegram import Bot
from telegram.error import TelegramError

from shiori_sdk.messages import InboundMessage

if TYPE_CHECKING:
    from shiori_sdk.channels.avatars import AvatarsCapability

# Anonymous senders post as a chat (a channel or the group itself): ``chat:<id>``.
_SENDER_CHAT_PREFIX = "chat:"
# The host shrinks avatars to 128px; the first photo size at least this wide suffices.
_AVATAR_MIN_WIDTH = 128

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


async def fetch_user_photo(bot: Bot, user_id: int) -> bytes | None:
    """A user's latest profile photo; None when they have none.

    Raises ``TelegramError`` when it cannot be fetched.
    """
    photos = await bot.get_user_profile_photos(user_id, limit=1)
    if not photos.photos:
        return None
    # Sizes are ordered smallest first.
    sizes = photos.photos[0]
    size = next((item for item in sizes if item.width >= _AVATAR_MIN_WIDTH), sizes[-1])
    file = await bot.get_file(size.file_id)
    return bytes(await file.download_as_bytearray())


async def fetch_chat_photo(bot: Bot, chat_id: str) -> bytes | None:
    """A chat's photo (a group's, or the other person's in a private chat).

    None when it has none; raises ``TelegramError`` when it cannot be fetched.
    """
    chat = await bot.get_chat(chat_id)
    if chat.photo is None:
        return None
    file = await bot.get_file(chat.photo.small_file_id)
    return bytes(await file.download_as_bytearray())


def refresh_message_avatars(
    avatars: AvatarsCapability, bot: Bot, message: InboundMessage
) -> None:
    """Asks the host to refresh the avatars an admitted message shows.

    The sender's profile photo (an anonymous sender chat's photo) and the
    chat's photo. The host fetches in the background and only when its cached
    one is due.
    """
    sender = message.sender
    if sender.startswith(_SENDER_CHAT_PREFIX):
        sender_chat = sender.removeprefix(_SENDER_CHAT_PREFIX)
        _ = avatars.refresh(
            "sender",
            message.channel,
            sender,
            lambda: fetch_chat_photo(bot, sender_chat),
        )
    else:
        _ = avatars.refresh(
            "sender",
            message.channel,
            sender,
            lambda: fetch_user_photo(bot, int(sender)),
        )
    _ = avatars.refresh(
        "chat",
        message.channel,
        message.chat_id,
        lambda: fetch_chat_photo(bot, message.chat_id),
    )
