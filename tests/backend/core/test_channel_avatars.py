"""channel_avatars.py 行为：认领到期、保存缩图、记录无头像、拒绝非图片与按键查询。"""

from __future__ import annotations

import io
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from PIL import Image

from core.channel_avatars import AVATAR_SIZE, AvatarKey, ChannelAvatarStore


def _png(size: int = 300) -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (size, size), "pink").save(output, format="PNG")
    return output.getvalue()


class _Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 9, 30, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.now


SENDER = AvatarKey("sender", "qq", "42")
GROUP = AvatarKey("chat", "qq", "gqq:5")


def _store(tmp_path: Path) -> tuple[ChannelAvatarStore, _Clock]:
    clock = _Clock()
    return ChannelAvatarStore(tmp_path, clock=clock), clock


def test_claim_is_due_without_cache_then_waits_seven_days(tmp_path: Path) -> None:
    store, clock = _store(tmp_path)

    assert store.claim(SENDER, plugin_id="qq") is True
    # 并发的第二次认领（或刚失败后的重试）未到期。
    assert store.claim(SENDER, plugin_id="qq") is False
    # 同一 ID 的会话头像是另一份。
    assert store.claim(AvatarKey("chat", "qq", "42"), plugin_id="qq") is True
    clock.now += timedelta(days=7) - timedelta(seconds=1)
    assert store.claim(SENDER, plugin_id="qq") is False
    clock.now += timedelta(seconds=1)
    assert store.claim(SENDER, plugin_id="qq") is True


def test_saved_avatar_is_a_small_png_kept_until_replaced(tmp_path: Path) -> None:
    store, clock = _store(tmp_path)

    store.save(GROUP, _png(), plugin_id="qq")

    path = store.index().chat("qq", "gqq:5")
    assert path is not None and path.startswith(str(tmp_path))
    with Image.open(path) as saved:
        assert saved.format == "PNG"
        assert max(saved.size) == AVATAR_SIZE
    assert store.claim(GROUP, plugin_id="qq") is False
    clock.now += timedelta(days=8)
    assert store.claim(GROUP, plugin_id="qq") is True
    # 到期重新认领时，新图到来前仍显示旧头像。
    assert store.index().chat("qq", "gqq:5") == path


def test_missing_avatar_falls_back_to_the_placeholder(tmp_path: Path) -> None:
    store, _ = _store(tmp_path)
    store.save(SENDER, _png(), plugin_id="qq")
    path = store.index().sender("qq", "42")
    assert path is not None

    store.mark_missing(SENDER, plugin_id="qq")

    assert store.index().sender("qq", "42") is None
    assert not Path(path).exists()
    assert store.claim(SENDER, plugin_id="qq") is False


@pytest.mark.parametrize(
    "image",
    [
        b"<html>not an image</html>",
        # 声称是 PNG 但无法解码。
        b"\x89PNG\r\n\x1a\n" + b"\x00" * 16,
        # 超过 1 MiB。
        b"\x89PNG\r\n\x1a\n" + b"\x00" * (1024 * 1024),
    ],
    ids=["html", "corrupt", "oversize"],
)
def test_oversize_or_non_image_input_is_refused(tmp_path: Path, image: bytes) -> None:
    store, _ = _store(tmp_path)
    store.save(SENDER, _png(), plugin_id="qq")
    before = store.index().sender("qq", "42")

    with pytest.raises(ValueError):
        store.save(SENDER, image, plugin_id="qq")

    assert store.index().sender("qq", "42") == before


def test_unknown_kind_or_blank_id_is_refused() -> None:
    with pytest.raises(ValueError):
        AvatarKey.parse("member", "qq", "42")
    with pytest.raises(ValueError):
        AvatarKey.parse("sender", "qq", " ")


def test_a_senders_avatars_are_listed_per_channel_newest_first(
    tmp_path: Path,
) -> None:
    store, clock = _store(tmp_path)
    store.save(AvatarKey("sender", "telegram_a", "7"), _png(), plugin_id="telegram")
    clock.now += timedelta(hours=1)
    store.save(AvatarKey("sender", "telegram_b", "7"), _png(), plugin_id="telegram")
    store.save(AvatarKey("chat", "telegram_b", "7"), _png(), plugin_id="telegram")

    index = store.index()

    assert [channel for channel, _ in index.sender_avatars("7")] == [
        "telegram_b",
        "telegram_a",
    ]
    assert index.sender_avatars("8") == []
