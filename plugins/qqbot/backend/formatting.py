from __future__ import annotations

from typing import Any, cast

import httpx

CHANNEL = "qqbot"
API_BASE = "https://api.sgroup.qq.com"
TOKEN_URL = "https://bots.qq.com/app/getAppAccessToken"
LIVE_STREAM_MIN_INTERVAL_S = 1.5
REPLY_LIVE_TAIL = 900
SUPPORTED_IMAGE_MIME_TYPES = {
    "image/gif",
    "image/jpeg",
    "image/png",
    "image/webp",
}
# Keeps the model from confusing the official bot with NapCat QQ (`qq`).
SYSTEM_PROMPT_HINT = (
    "## 官方 QQBot 渠道规则（硬性）"
    "\n- 当前会话是官方 QQBot，另外向用户发送消息或图片时用 `account_send` 的 `channel=qqbot`。"
    "\n- 不得把官方 QQBot 写成 `channel=qq`；`qq` 仅指 NapCat QQ。"
)


def as_dict(value: object) -> dict[str, Any]:
    return cast(dict[str, Any], value) if isinstance(value, dict) else {}


def http_status_code(error: Exception) -> int | None:
    if isinstance(error, httpx.HTTPStatusError):
        return error.response.status_code
    return None


def format_turn_live(reply: str) -> str:
    return tail_text(reply.strip(), REPLY_LIVE_TAIL)


def tail_text(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return "..." + text[-(limit - 3) :]
