"""Feishu / Lark bot avatars downloaded into data URIs for the account list."""

from __future__ import annotations

import logging

import httpx

from core.accounts import avatar_data_uri

from .api import FeishuApi

logger = logging.getLogger(__name__)


async def fetch_bot_avatar(api: FeishuApi, avatar_url: str) -> str | None:
    """Downloads ``bot.avatar_url`` from ``/open-apis/bot/v3/info``.

    Returns "" when the bot has no avatar and None when it cannot be fetched;
    a network boundary, so failures are logged and never raised.
    """
    if not avatar_url:
        return ""
    try:
        return avatar_data_uri(await api.fetch_url(avatar_url))
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("[feishu] 机器人头像获取失败: %s", exc)
        return None
