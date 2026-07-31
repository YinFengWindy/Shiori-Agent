"""Day-level narrative grouping and progression for persistent worlds."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable

from world_simulation.timeline import TimelineEvent


@dataclass(frozen=True)
class WorldDayGroup:
    """One ordered Day chapter derived from committed timeline events."""

    day_index: int
    status: str
    events: tuple[TimelineEvent, ...]


def current_day_index(events: Iterable[TimelineEvent]) -> int:
    """Return the latest structured Day without parsing display labels."""

    return max((event.day_index for event in events), default=1)


def group_world_days(events: Iterable[TimelineEvent]) -> tuple[WorldDayGroup, ...]:
    """Group committed facts into ordered completed/current Day chapters."""

    ordered = tuple(events)
    current = current_day_index(ordered)
    indexes = sorted({event.day_index for event in ordered} or {1})
    return tuple(
        WorldDayGroup(
            day_index=index,
            status="current" if index == current else "completed",
            events=tuple(event for event in ordered if event.day_index == index),
        )
        for index in indexes
    )


def next_day_time(value: str) -> str:
    """Advance an ISO world clock by one Day while preserving timezone semantics."""

    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return value
    return (parsed + timedelta(days=1)).astimezone(timezone.utc).isoformat()
