"""Draft application verification, separate from the live WebSocket."""

from __future__ import annotations

import httpx
from collections.abc import Callable

from .api import FeishuApi
from .config import FeishuAppConfig


async def verify_app(
    app: FeishuAppConfig,
    *,
    resolver: Callable[[str], str],
    transport: httpx.AsyncBaseTransport | None = None,
) -> dict[str, str]:
    """Authenticates a draft without replacing a live account connection."""
    secret = app.resolved_secret(resolver)
    if not secret:
        raise ValueError("App ID 和 App Secret 必须有效")
    api = FeishuApi(app.app_id, secret, app.base_url, transport=transport)
    api.open()
    try:
        identity = await api.bot_info()
    finally:
        await api.aclose()
    if not identity.get("open_id"):
        raise ValueError("飞书机器人身份响应缺少 open_id")
    return {
        "name": str(identity.get("app_name") or ""),
        "open_id": str(identity["open_id"]),
    }
