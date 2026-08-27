import pytest

from story_simulation.story_time import (
    next_story_clock,
    next_story_time_band,
    normalize_story_time_band,
)


def test_next_story_time_band_keeps_the_current_period_without_director_change() -> None:
    assert next_story_time_band("上午") == "上午"


def test_next_story_time_band_accepts_only_an_explicit_period_change() -> None:
    assert next_story_time_band("上午", "夜晚") == "夜晚"
    with pytest.raises(ValueError, match="time_band"):
        next_story_time_band("上午", "2026-08-01T10:00")


def test_next_story_clock_keeps_the_selected_date_when_period_moves_forward() -> None:
    assert next_story_clock("2026-08-01", "上午", "夜晚") == ("2026-08-01", "夜晚")


def test_next_story_clock_advances_the_selected_date_when_period_wraps_midnight() -> None:
    assert next_story_clock("2026-08-01", "深夜", "清晨") == ("2026-08-02", "清晨")


def test_normalize_story_time_band_rejects_exact_timestamps() -> None:
    assert normalize_story_time_band("下午") == "下午"
    with pytest.raises(ValueError, match="time_band"):
        normalize_story_time_band("2026-08-01T10:00:00+08:00")
