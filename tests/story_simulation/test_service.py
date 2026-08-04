from __future__ import annotations

from collections.abc import Sequence

import pytest

from story_simulation.director import StoryDirector
from story_simulation.errors import StoryInvalidOutputError
from story_simulation.models import DirectorDraft, StoryBeatDraft, StoryPlayerProfile
from story_simulation.repository import StoryRepository, payload_hash
from story_simulation.service import StorySimulationService


class SequencedDirector(StoryDirector):
    """Return deterministic drafts or failures for Story service tests."""

    def __init__(self, outcomes: Sequence[DirectorDraft | Exception]) -> None:
        self.outcomes = list(outcomes)
        self.calls = 0

    async def generate(self, **_kwargs) -> DirectorDraft:
        outcome = self.outcomes[self.calls]
        self.calls += 1
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _service(tmp_path, outcomes: Sequence[DirectorDraft | Exception]):
    repository = StoryRepository(tmp_path / "story.db")
    repository.create_story(
        story_id="story-1",
        title="夏日来信",
        background="午后的旧校舍",
        role_snapshot={"id": "role-1", "name": "澪"},
        player_profile=StoryPlayerProfile("悠", "短发", "转学生"),
        story_date="2026-08-01",
        time_band="上午",
        opening_context={},
    )
    director = SequencedDirector(outcomes)
    return StorySimulationService(repository=repository, director=director), director


@pytest.mark.asyncio
async def test_service_retries_invalid_draft_once_before_committing(tmp_path) -> None:
    draft = DirectorDraft(
        beats=(
            StoryBeatDraft(text="风从走廊尽头吹来。"),
            StoryBeatDraft(text="澪抬眼看向你。", kind="dialogue", speaker="澪", time_band="夜晚"),
        )
    )
    service, director = _service(tmp_path, [StoryInvalidOutputError("bad json"), draft])
    turn = service.create_player_turn(
        story_id="story-1",
        input_text="推开门",
        request_id="request-1",
        request_payload_hash=payload_hash({"input": "推开门"}),
        expected_revision=0,
    )
    events: list[dict] = []

    await service.generate_turn(turn, events.append)

    story = service.repository.story_read_model("story-1")
    assert director.calls == 2
    assert story["turns"][0]["status"] == "committed"
    assert [cue["text"] for cue in story["cues"]] == ["风从走廊尽头吹来。", "澪抬眼看向你。"]
    assert [beat["storyDate"] for beat in story["beats"]] == ["2026-08-01", "2026-08-01"]
    assert [beat["timeBand"] for beat in story["beats"]] == ["上午", "夜晚"]
    assert story["currentTimeBand"] == "夜晚"
    assert [event["method"] for event in events] == [
        "stories.beat.committed",
        "stories.beat.committed",
        "stories.operation.changed",
    ]


@pytest.mark.asyncio
async def test_service_does_not_commit_beats_after_final_failure(tmp_path) -> None:
    service, director = _service(
        tmp_path,
        [StoryInvalidOutputError("bad json"), StoryInvalidOutputError("bad json")],
    )
    turn = service.create_player_turn(
        story_id="story-1",
        input_text="推开门",
        request_id="request-1",
        request_payload_hash=payload_hash({"input": "推开门"}),
        expected_revision=0,
    )
    events: list[dict] = []

    await service.generate_turn(turn, events.append)

    story = service.repository.story_read_model("story-1")
    assert director.calls == 2
    assert story["beats"] == []
    assert story["cues"] == []
    assert story["turns"][0]["status"] == "failed"
    assert events[-1]["method"] == "stories.failed"
