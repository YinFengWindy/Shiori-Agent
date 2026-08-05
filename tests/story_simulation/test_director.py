import json

import pytest

from story_simulation.director import ProviderStoryDirector
from story_simulation.errors import StoryInvalidOutputError


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
                ]
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
            }
        )
    )

    assert draft.visual_type == "character"
    assert draft.visual_prompt == "girl, umbrella, rainy street"


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
