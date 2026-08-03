from story_simulation.story_time import next_story_time


def test_next_story_time_starts_at_the_story_start() -> None:
    assert next_story_time("2026-08-01T09:00:00+08:00", initial=True) == "2026-08-01T09:00:00+08:00"


def test_next_story_time_advances_when_the_director_omits_or_rewinds_time() -> None:
    current = "2026-08-01T09:00:00+08:00"
    assert next_story_time(current) == "2026-08-01T09:30:00+08:00"
    assert next_story_time(current, "2026-08-01T08:00:00+08:00") == "2026-08-01T09:30:00+08:00"


def test_next_story_time_keeps_a_later_director_time() -> None:
    assert next_story_time("2026-08-01T09:00:00+08:00", "2026-08-01T11:00:00+08:00") == "2026-08-01T11:00:00+08:00"
