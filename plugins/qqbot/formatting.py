from __future__ import annotations

from typing import Any, cast

import httpx

CHANNEL = "qqbot"
API_BASE = "https://api.sgroup.qq.com"
TOKEN_URL = "https://bots.qq.com/app/getAppAccessToken"
LIVE_STREAM_MIN_CHARS = 120
LIVE_STREAM_MIN_INTERVAL_S = 1.5
LIVE_MAX_FAILURES = 3
REPLY_LIVE_TAIL = 900
SUPPORTED_IMAGE_MIME_TYPES = {
    "image/gif",
    "image/jpeg",
    "image/png",
    "image/webp",
}


def as_dict(value: object) -> dict[str, Any]:
    return cast(dict[str, Any], value) if isinstance(value, dict) else {}


def http_status_code(error: Exception) -> int | None:
    if isinstance(error, httpx.HTTPStatusError):
        return error.response.status_code
    return None


def iter_stream_chunks(text: str, limit: int = 160) -> list[str]:
    if not text:
        return [""]
    return [text[:end] for end in range(limit, len(text) + limit, limit)]


def format_turn_live(reply: str) -> str:
    return tail_text(reply.strip(), REPLY_LIVE_TAIL)


def tail_text(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return "..." + text[-(limit - 3) :]
