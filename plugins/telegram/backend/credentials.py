"""Verify a draft Bot Token without changing any running connection."""

from typing import Any

from telegram import Bot
from telegram.error import TelegramError


async def verify_bot_token(payload: dict[str, Any]) -> dict[str, str]:
    """Return the authenticated Bot identity without echoing its credential."""
    token = str(payload.get("token") or "").strip()
    if not token:
        raise ValueError("Bot Token is required")
    try:
        async with Bot(token) as bot:
            identity = await bot.get_me()
    except (TelegramError, ValueError) as exc:
        raise ValueError("Bot Token 验证失败；请检查凭据和网络连接") from exc
    return {
        "bot_id": str(identity.id),
        "name": identity.full_name,
        "username": identity.username or "",
    }
