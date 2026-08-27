from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

_BEIJING_TZ = ZoneInfo("Asia/Shanghai")


def to_beijing_time(value: datetime) -> datetime:
    """Converts an aware or naive datetime to Beijing time."""
    if value.tzinfo is None:
        return value.replace(tzinfo=_BEIJING_TZ)
    return value.astimezone(_BEIJING_TZ)


def format_beijing_timestamp(raw: object) -> str:
    """Formats an ISO timestamp for proactive prompt context."""
    if isinstance(raw, datetime):
        value = raw
    else:
        text = str(raw or "").strip()
        if not text:
            return ""
        try:
            value = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return ""
    return to_beijing_time(value).strftime("%Y-%m-%d %H:%M:%S %z")
