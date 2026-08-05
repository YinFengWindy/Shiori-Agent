import json

import pytest

from story_simulation.director import ProviderStoryDirector
from story_simulation.errors import StoryInvalidOutputError
from story_simulation.models import StoryContext


def test_director_parser_keeps_only_an_explicit_time_band() -> None:
    draft = ProviderStoryDirector._parse(
        json.dumps(
            {
                "beats": [
                    {
                        "text": "天色渐暗。",
                        "kind": "narration",
                        "speaker": None,
                        "time_band": "夜晚",
                        "effective_at": "2026-08-01T20:00:00+08:00",
                    }
                ],
                "current_scene": {"key": "school-rooftop", "character_ids": []},
            },
            ensure_ascii=False,
        )
    )

    assert draft.beats[0].time_band == "夜晚"
    assert not hasattr(draft.beats[0], "effective_at")


def test_director_parser_accepts_character_visual_type() -> None:
    draft = ProviderStoryDirector._parse(
        json.dumps(
            {
                "beats": [{"text": "她转身挡在你身前。"}],
                "visual_type": "character",
                "visual_prompt": "girl, umbrella, rainy street",
                "current_scene": {"key": "rainy-street", "character_ids": ["role-1", "player"]},
            }
        )
    )

    assert draft.visual_type == "character"
    assert draft.visual_prompt == "girl, umbrella, rainy street"
    assert draft.current_scene.key == "rainy-street"
    assert draft.current_scene.character_ids == ("role-1", "player")


def test_director_parser_rejects_unknown_visual_type() -> None:
    with pytest.raises(StoryInvalidOutputError, match="visual_type"):
        ProviderStoryDirector._parse(
            json.dumps({"beats": [{"text": "门开了。"}], "visual_type": "portrait"})
        )


def test_director_prompt_requires_novelai_v45_directional_tags() -> None:
    prompt = ProviderStoryDirector._system_prompt()

    assert "NovelAI V4.5" in prompt
    assert "player_profile.appearance" in prompt
    assert "{girl feeding boy}" in prompt
    assert "不能使用 :1.2 数字权重" in prompt
    assert "white background" not in prompt
    assert "current_scene" in prompt
    assert "character_ids" in prompt


def test_director_request_carries_the_persisted_current_scene() -> None:
    payload = ProviderStoryDirector._request_payload(
        StoryContext(
            story={"title": "雨港", "background": "车站"},
            role_snapshot={"id": "role-1", "name": "澪"},
            player_profile={},
            segment={
                "storyDate": "2026-08-01",
                "timeBand": "上午",
                "runtimeSnapshot": {
                    "current_scene": {"key": "station", "character_ids": ["role-1"]},
                },
            },
        ),
        "继续。",
        False,
    )

    assert payload["story"]["current_scene"] == {
        "key": "station",
        "character_ids": ["role-1"],
    }


def test_director_parser_requires_current_scene() -> None:
    with pytest.raises(StoryInvalidOutputError, match="current_scene"):
        ProviderStoryDirector._parse(json.dumps({"beats": [{"text": "门开了。"}]}))
