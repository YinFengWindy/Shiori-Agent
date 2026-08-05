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
