"""QQ avatars fetched from the public QQ avatar service.

The account's own avatar becomes a data URI for its host registration; the
avatars of message senders and groups go to the host's cache (``ctx.avatars``).
"""

from __future__ import annotations

import base64
import logging
from typing import TYPE_CHECKING

import httpx

from bus.events import InboundMessage
from core.net.http import shared_ssl_context

if TYPE_CHECKING:
    from agent.plugin_host.avatars import AvatarsCapability

logger = logging.getLogger(__name__)

QQ_AVATAR_URL = "https://q1.qlogo.cn/g?b=qq&nk={uin}&s=100"
QQ_GROUP_AVATAR_URL = "https://p.qlogo.cn/gh/{group}/{group}/100"
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


async def download_avatar(
    url: str, *, transport: httpx.AsyncBaseTransport | None = None
) -> bytes:
    """The image bytes at a QQ avatar ``url``; raises ``httpx.HTTPError``."""
    async with httpx.AsyncClient(
        timeout=10.0, transport=transport, verify=shared_ssl_context()
    ) as client:
        response = await client.get(url, follow_redirects=True)
        _ = response.raise_for_status()
    return response.content


async def fetch_qq_avatar(
    uin: str, *, transport: httpx.AsyncBaseTransport | None = None
) -> str | None:
    """The QQ number's 100px avatar as a data URI; None when it cannot be fetched.

    A network boundary: failures are logged, never raised, so a connection
    never fails because of its avatar.
    """
    try:
        content = await download_avatar(
            QQ_AVATAR_URL.format(uin=uin), transport=transport
        )
        return _avatar_data_uri(content)
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("[qq] 账号 %s 头像获取失败: %s", uin, exc)
        return None


def refresh_message_avatars(
    avatars: AvatarsCapability, message: InboundMessage
) -> None:
    """Asks the host to refresh the avatars an admitted message shows.

    The sender's avatar by QQ number; the chat's avatar is the group's (by
    group number) for a group and the sender's for a private chat. The host
    fetches in the background and only when its cached one is due.
    """
    sender_url = QQ_AVATAR_URL.format(uin=message.sender)
    _ = avatars.refresh(
        "sender", message.channel, message.sender, lambda: download_avatar(sender_url)
    )
    chat_url = (
        QQ_GROUP_AVATAR_URL.format(group=message.metadata["group_id"])
        if message.metadata.get("chat_type") == "group"
        else sender_url
    )
    _ = avatars.refresh(
        "chat", message.channel, message.chat_id, lambda: download_avatar(chat_url)
    )
