"""QQBot application avatars, read from the bot's own ``/users/@me`` profile."""

from __future__ import annotations

import base64
import logging
from typing import TYPE_CHECKING

import httpx

from .gateway import QQBotAuthenticationError

if TYPE_CHECKING:
    from .channel import QQBotChannel

logger = logging.getLogger(__name__)

# The host refuses larger avatars.
_MAX_AVATAR_BYTES = 256 * 1024


def _avatar_data_uri(content: bytes) -> str:
    """The downloaded image as the ``data:`` URI the host accepts."""
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        mime = "image/png"
    elif content.startswith(b"\xff\xd8\xff"):
        mime = "image/jpeg"
    elif content.startswith((b"GIF87a", b"GIF89a")):
        mime = "image/gif"
    elif content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        mime = "image/webp"
    else:
        raise ValueError("QQBot 头像不是 PNG、JPEG、GIF 或 WebP 图片")
    if len(content) > _MAX_AVATAR_BYTES:
        raise ValueError("QQBot 头像超过 256 KiB")
    return f"data:{mime};base64,{base64.b64encode(content).decode('ascii')}"


async def fetch_bot_avatar(channel: QQBotChannel) -> str | None:
    """The connected bot's avatar as a data URI, through its own REST client.

    Returns "" when the bot has no avatar and None when it cannot be fetched;
    a network boundary, so failures are logged and never raised.
    """
    try:
        profile = await channel._api_request("GET", "/users/@me")
        url = str(profile.get("avatar") or "")
        if not url:
            return ""
        response = await channel._http_client().get(url, follow_redirects=True)
        response.raise_for_status()
        return _avatar_data_uri(response.content)
    except (httpx.HTTPError, QQBotAuthenticationError, ValueError) as exc:
        logger.warning("[qqbot] 机器人头像获取失败: %s", exc)
        return None
