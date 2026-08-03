"""Story-local clock rules used when committing narrative beats."""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

STORY_TIMEZONE = ZoneInfo("Asia/Shanghai")
STORY_BEAT_TIME_STEP = timedelta(minutes=30)


def normalize_story_time(value: str) -> datetime:
    """Parse one Story timestamp and normalize it to Beijing time."""

    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError("Story 时间必须带时区")
    return parsed.astimezone(STORY_TIMEZONE)


def next_story_time(
    current_at: str,
    requested_at: str | None = None,
    *,
    initial: bool = False,
) -> str:
    """Return a monotonic beat time, advancing when the Director omits one."""

    current = normalize_story_time(current_at)
    if requested_at:
        try:
            requested = normalize_story_time(requested_at)
        except ValueError:
            requested = None
        if requested is not None and requested > current:
            return requested.isoformat()
    if initial:
        return current.isoformat()
    return (current + STORY_BEAT_TIME_STEP).isoformat()
