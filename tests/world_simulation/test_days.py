from world_simulation.days import current_day_index, group_world_days, next_day_time
from world_simulation.timeline import TimelineEvent


def _event(event_id: str, sequence: int, day_index: int) -> TimelineEvent:
    return TimelineEvent(
        id=event_id,
        world_id="world-1",
        event_type="story.event",
        effective_at=f"2026-07-{day_index:02d}T00:00:00+00:00",
        sequence=sequence,
        day_index=day_index,
    )


def test_groups_committed_events_into_ordered_day_chapters() -> None:
    events = (_event("day-1", 1, 1), _event("day-2-a", 2, 2), _event("day-2-b", 3, 2))

    days = group_world_days(events)

    assert current_day_index(events) == 2
    assert [day.status for day in days] == ["completed", "current"]
    assert [event.id for event in days[1].events] == ["day-2-a", "day-2-b"]


def test_advances_iso_world_time_by_one_day_without_parsing_display_labels() -> None:
    assert next_day_time("2026-07-31T08:00:00+00:00") == "2026-08-01T08:00:00+00:00"
    assert next_day_time("序章") == "序章"
