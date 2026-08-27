"""Five-period Story clock rules."""

from __future__ import annotations

from datetime import date, timedelta
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


def normalize_story_date(value: str) -> str:
    """Validate and normalize the player-selected Story calendar date."""

    normalized = value.strip()
    try:
        parsed = date.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError("Story story_date 无效") from exc
    if parsed.isoformat() != normalized:
        raise ValueError("Story story_date 必须是 YYYY-MM-DD")
    return parsed.isoformat()


def next_story_time_band(
    current_band: str, requested_band: str | None = None
) -> StoryTimeBand:
    """Keep the current period unless the Director explicitly changes it."""

    current = normalize_story_time_band(current_band)
    if requested_band is None or not requested_band.strip():
        return current
    return normalize_story_time_band(requested_band)


def next_story_clock(
    current_date: str, current_band: str, requested_band: str | None = None
) -> tuple[str, StoryTimeBand]:
    """Advance the five-period Story clock without consulting system time."""

    story_date = date.fromisoformat(normalize_story_date(current_date))
    current = normalize_story_time_band(current_band)
    next_band = next_story_time_band(current, requested_band)
    if next_band != current and STORY_TIME_BANDS.index(next_band) < STORY_TIME_BANDS.index(current):
        story_date += timedelta(days=1)
    return story_date.isoformat(), next_band
