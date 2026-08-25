from story_simulation._json import dump as legacy_dump
from story_simulation._json import load as legacy_load
from story_simulation.internal._json import dump, load


def test_json_helpers_keep_legacy_exports_compatible() -> None:
    payload = {"b": 2, "a": "故事"}

    assert dump(payload) == legacy_dump(payload)
    encoded = dump(payload)
    assert load(encoded, {}) == legacy_load(encoded, {}) == payload
    assert load("invalid", None) is None

