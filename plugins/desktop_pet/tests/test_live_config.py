"""Per-role live settings: validated whole-document saves in private storage."""

import pytest
from pydantic import ValidationError

from plugins.desktop_pet.backend.live_config import LiveConfig, LiveConfigStore


def test_defaults_save_and_prune(tmp_path):
    store = LiveConfigStore(tmp_path)
    assert store.read("mira") == LiveConfig()
    saved = store.write(
        "mira", {"room_id": 6, "reply_interval_seconds": 3, "wait_timeout_seconds": 20}
    )
    assert store.read("mira") == saved
    store.prune({"other"})
    assert store.read("mira") == LiveConfig()


@pytest.mark.parametrize(
    "values",
    [
        {"room_id": 0},
        {"room_id": "6"},
        {"reply_interval_seconds": -1},
        {"wait_timeout_seconds": 1},
        {"capacity": 5},
    ],
)
def test_invalid_values_are_rejected_without_writing(tmp_path, values):
    store = LiveConfigStore(tmp_path)
    with pytest.raises(ValidationError):
        store.write("mira", values)
    assert not store.root.exists()
