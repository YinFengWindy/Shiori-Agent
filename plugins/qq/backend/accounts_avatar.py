"""QQ account avatars fetched from the public QQ avatar service."""

from __future__ import annotations

import base64
import logging

import httpx

from core.net.http import shared_ssl_context

logger = logging.getLogger(__name__)

QQ_AVATAR_URL = "https://q1.qlogo.cn/g?b=qq&nk={uin}&s=100"
# The host refuses larger avatars; a 100px avatar is a few KiB.
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
        raise ValueError("QQ 头像不是 PNG、JPEG、GIF 或 WebP 图片")
    if len(content) > _MAX_AVATAR_BYTES:
        raise ValueError("QQ 头像超过 256 KiB")
    return f"data:{mime};base64,{base64.b64encode(content).decode('ascii')}"


async def fetch_qq_avatar(
    uin: str, *, transport: httpx.AsyncBaseTransport | None = None
) -> str | None:
    """The QQ number's 100px avatar as a data URI; None when it cannot be fetched.

    A network boundary: failures are logged, never raised, so a connection
    never fails because of its avatar.
    """
    try:
        async with httpx.AsyncClient(
            timeout=10.0, transport=transport, verify=shared_ssl_context()
        ) as client:
            response = await client.get(
                QQ_AVATAR_URL.format(uin=uin), follow_redirects=True
            )
            response.raise_for_status()
        return _avatar_data_uri(response.content)
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("[qq] 账号 %s 头像获取失败: %s", uin, exc)
        return None
