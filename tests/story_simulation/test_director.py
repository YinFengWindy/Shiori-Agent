import json

from story_simulation.director import ProviderStoryDirector


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
