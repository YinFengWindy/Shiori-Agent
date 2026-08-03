from __future__ import annotations

import pytest

from story_simulation.models import StoryPlayerProfile
from story_simulation.repository import StoryRepository, payload_hash


def _create_story(repository: StoryRepository) -> None:
    repository.create_story(
        story_id="story-1",
        title="夏日来信",
        background="午后的旧校舍",
        role_snapshot={"id": "role-1", "name": "澪"},
        player_profile=StoryPlayerProfile("悠", "短发", "转学生"),
        time_band="上午",
        opening_context={"background": "午后的旧校舍"},
    )


def test_story_repository_freezes_opening_profile_and_replays_same_turn(tmp_path) -> None:
    repository = StoryRepository(tmp_path / "story.db")
    _create_story(repository)

    request = {"story_id": "story-1", "input": "推开门", "expected_revision": 0}
    turn = repository.create_turn(
        story_id="story-1",
        input_text="推开门",
        request_id="request-1",
        request_payload_hash=payload_hash(request),
        expected_revision=0,
    )
    replay = repository.create_turn(
        story_id="story-1",
        input_text="推开门",
        request_id="request-1",
        request_payload_hash=payload_hash(request),
        expected_revision=999,
    )

    story = repository.story_read_model("story-1")
    assert story["playerProfile"] == {
        "display_name": "悠",
        "appearance": "短发",
        "identity": "转学生",
    }
    assert story["roleSnapshot"] == {"id": "role-1", "name": "澪"}
    assert story["currentTimeBand"] == "上午"
    assert story["segment"]["timeBand"] == "上午"
    assert replay["id"] == turn["id"]

    with pytest.raises(ValueError, match="不同的请求"):
        repository.create_turn(
            story_id="story-1",
            input_text="转身离开",
            request_id="request-1",
            request_payload_hash=payload_hash({**request, "input": "转身离开"}),
            expected_revision=0,
        )

    repository.close()
    restarted = StoryRepository(tmp_path / "story.db")
    assert restarted.story_read_model("story-1")["turns"][0]["id"] == turn["id"]
    restarted.close()
