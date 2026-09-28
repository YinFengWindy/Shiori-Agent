"""Feishu / Lark bot avatars downloaded into data URIs for the account list."""

from __future__ import annotations

import base64
import logging

import httpx

from .api import FeishuApi

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
        raise ValueError("飞书机器人头像不是 PNG、JPEG、GIF 或 WebP 图片")
    if len(content) > _MAX_AVATAR_BYTES:
        raise ValueError("飞书机器人头像超过 256 KiB")
    return f"data:{mime};base64,{base64.b64encode(content).decode('ascii')}"


async def fetch_bot_avatar(api: FeishuApi, avatar_url: str) -> str | None:
    """Downloads ``bot.avatar_url`` from ``/open-apis/bot/v3/info``.

    Returns "" when the bot has no avatar and None when it cannot be fetched;
    a network boundary, so failures are logged and never raised.
    """
    if not avatar_url:
        return ""
    try:
        return _avatar_data_uri(await api.fetch_url(avatar_url))
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("[feishu] 机器人头像获取失败: %s", exc)
        return None
