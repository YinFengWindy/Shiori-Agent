"""QQBot application avatars, read from the bot's own ``/users/@me`` profile."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import httpx

from core.accounts import avatar_data_uri

from .gateway import QQBotAuthenticationError

if TYPE_CHECKING:
    from .channel import QQBotChannel

logger = logging.getLogger(__name__)


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
        return avatar_data_uri(response.content)
    except (httpx.HTTPError, QQBotAuthenticationError, ValueError) as exc:
        logger.warning("[qqbot] 机器人头像获取失败: %s", exc)
        return None
