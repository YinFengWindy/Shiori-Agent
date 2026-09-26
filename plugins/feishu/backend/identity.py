"""Draft application verification, separate from the live WebSocket."""

from __future__ import annotations

import httpx

from agent.config import resolve_config_references

from .api import FeishuApi
from .config import FeishuAppConfig, UNRESOLVED_ENV_RE


async def verify_app(
    app: FeishuAppConfig, *, transport: httpx.AsyncBaseTransport | None = None
) -> dict[str, str]:
    """Authenticates a draft without replacing a live account connection."""
    secret = str(resolve_config_references(app.app_secret))
    if not app.app_id or not secret or UNRESOLVED_ENV_RE.fullmatch(secret):
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
