"""Per-role live settings: partial validated saves with Chinese errors."""

import pytest

from plugins.desktop_pet.backend.live_config import LiveConfig, LiveConfigStore


def test_updates_merge_only_the_given_fields_and_prune(tmp_path):
    store = LiveConfigStore(tmp_path)
    assert store.read("mira") == LiveConfig()
    store.update("mira", {"room_id": 6, "wait_timeout_seconds": 20})
    saved = store.update("mira", {"reply_interval_seconds": 3})
    assert saved == LiveConfig(
        room_id=6, reply_interval_seconds=3, wait_timeout_seconds=20
    )
    assert store.read("mira") == saved
    store.prune({"other"})
    assert store.read("mira") == LiveConfig()


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"room_id": 0}, "直播间号必须是正整数"),
        ({"room_id": "6"}, "直播间号必须是正整数"),
        ({"reply_interval_seconds": -1}, "回复间隔必须是 0–300 之间的整数秒"),
        ({"wait_timeout_seconds": 1}, "等待时限必须是 5–600 之间的整数秒"),
        ({"capacity": 5}, "不支持的直播设置项: capacity"),
    ],
)
def test_invalid_values_explain_themselves_and_write_nothing(
    tmp_path, changes, message
):
    store = LiveConfigStore(tmp_path)
    with pytest.raises(ValueError) as error:
        store.update("mira", changes)
    assert str(error.value) == message
    assert not store.root.exists()
