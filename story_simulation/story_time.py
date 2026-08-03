"""Five-period Story clock rules."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, cast
from zoneinfo import ZoneInfo

STORY_TIME_BANDS = ("清晨", "上午", "下午", "夜晚", "深夜")
StoryTimeBand = Literal["清晨", "上午", "下午", "夜晚", "深夜"]
STORY_TIMEZONE = ZoneInfo("Asia/Shanghai")


def normalize_story_time_band(value: str) -> StoryTimeBand:
    """Validate and return one of the five player-facing Story periods."""

    normalized = value.strip()
    if normalized not in STORY_TIME_BANDS:
        raise ValueError("Story time_band 无效")
    return cast(StoryTimeBand, normalized)


def next_story_time_band(
    current_band: str, requested_band: str | None = None
) -> StoryTimeBand:
    """Keep the current period unless the Director explicitly changes it."""

    current = normalize_story_time_band(current_band)
    if requested_band is None or not requested_band.strip():
        return current
    return normalize_story_time_band(requested_band)


def legacy_story_time_band(value: str) -> StoryTimeBand:
    """Convert a pre-band Story timestamp while migrating an existing database."""

    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("旧 Story 时间无效") from exc
    if parsed.tzinfo is None:
        raise ValueError("旧 Story 时间必须带时区")
    hour = parsed.astimezone(STORY_TIMEZONE).hour
    if 5 <= hour < 9:
        return "清晨"
    if 9 <= hour < 12:
        return "上午"
    if 12 <= hour < 18:
        return "下午"
    if 18 <= hour < 23:
        return "夜晚"
    return "深夜"
