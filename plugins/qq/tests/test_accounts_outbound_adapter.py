"""QQ role replies: group replies @ their trigger; receipts carry the snapshot."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from shiori_sdk.messages import OutboundMessage
from shiori_sdk.testing.channel_context import fake_channel_context
from shiori_sdk.testing.channel_hub import FakeChannelHub
from plugins.qq.backend.accounts_actions import qq_image_segment
from plugins.qq.backend.accounts_outbound_adapter import QQOutboundAdapter

_VIA = {
    "platform": "qq",
    "platform_account_id": "101",
    "display_name": "小栞",
    "prefix": "QQ 号「小栞」（101）",
}


class _Adapter(QQOutboundAdapter):
    def __init__(self, tmp_path: Path) -> None:
        self._sockets = {}
        self.hub = FakeChannelHub()
        self._ctx = fake_channel_context(tmp_path, channel_hub=self.hub)
        self.send_target = AsyncMock(return_value={"message_id": "88"})

    def via_account(self, account_id: str) -> dict[str, str]:
        assert account_id == "qq:101"
        return _VIA


def _receipts(adapter: _Adapter) -> list[tuple[object, object, object]]:
    return [
        (item["delivery_status"], item["external_message_id"], item["via_account"])
        for item in adapter.hub.deliveries
    ]


def _reply(
    chat_id: str,
    content: str = "好",
    media: list[str] | None = None,
    **metadata: object,
) -> OutboundMessage:
    return OutboundMessage(
        channel="qq",
        chat_id=chat_id,
        content=content,
        media=media or [],
        metadata={"account_id": "qq:101", "sender_id": "902", **metadata},
        committed_message_id="committed",
    )


@pytest.mark.asyncio
async def test_group_reply_mentions_trigger_then_chosen_members(tmp_path: Path) -> None:
    adapter = _Adapter(tmp_path)
    message = _reply("gqq:777", chat_type="group", mention_ids=["903", "902"])

    await adapter._on_response(message)

    adapter.send_target.assert_awaited_once_with(
        "qq:101", "group", "777", "好", mention_ids=("902", "903"), images=()
    )
    assert _receipts(adapter) == [("sent", "88", _VIA)]


@pytest.mark.asyncio
async def test_private_reply_mentions_nobody(tmp_path: Path) -> None:
    adapter = _Adapter(tmp_path)

    await adapter._on_response(_reply("902", chat_type="private", mention_ids=["9"]))

    adapter.send_target.assert_awaited_once_with(
        "qq:101", "private", "902", "好", mention_ids=(), images=()
    )


@pytest.mark.asyncio
async def test_group_reply_skips_unusable_chosen_mentions_and_still_sends(
    caplog: pytest.LogCaptureFixture, tmp_path: Path
) -> None:
    adapter = _Adapter(tmp_path)
    message = _reply("gqq:777", chat_type="group", mention_ids=["小明", "903"])

    with caplog.at_level("WARNING"):
        await adapter._on_response(message)

    adapter.send_target.assert_awaited_once_with(
        "qq:101", "group", "777", "好", mention_ids=("902", "903"), images=()
    )
    assert [status for status, _id, _via in _receipts(adapter)] == ["sent"]
    assert "小明" in caplog.text


@pytest.mark.asyncio
async def test_private_reply_sends_its_images_with_the_text(tmp_path: Path) -> None:
    adapter = _Adapter(tmp_path)

    await adapter._on_response(
        _reply("902", media=["/cg/a.png", "https://x/b.png"], chat_type="private")
    )

    adapter.send_target.assert_awaited_once_with(
        "qq:101",
        "private",
        "902",
        "好",
        mention_ids=(),
        images=("/cg/a.png", "https://x/b.png"),
    )


@pytest.mark.asyncio
async def test_group_reply_sends_images_and_keeps_mentions(tmp_path: Path) -> None:
    adapter = _Adapter(tmp_path)
    message = _reply(
        "gqq:777", media=["/cg/a.png"], chat_type="group", mention_ids=["903"]
    )

    await adapter._on_response(message)

    adapter.send_target.assert_awaited_once_with(
        "qq:101",
        "group",
        "777",
        "好",
        mention_ids=("902", "903"),
        images=("/cg/a.png",),
    )
    assert _receipts(adapter) == [("sent", "88", _VIA)]


@pytest.mark.asyncio
async def test_image_only_reply_is_sent(tmp_path: Path) -> None:
    adapter = _Adapter(tmp_path)

    await adapter._on_response(
        _reply("902", content="", media=["/cg/a.png"], chat_type="private")
    )

    adapter.send_target.assert_awaited_once_with(
        "qq:101", "private", "902", "", mention_ids=(), images=("/cg/a.png",)
    )
    assert [status for status, _id, _via in _receipts(adapter)] == ["sent"]


@pytest.mark.asyncio
async def test_invalid_local_image_marks_the_reply_failed(tmp_path: Path) -> None:
    adapter = _Adapter(tmp_path)

    async def build_message(
        *_args: object, images: tuple[str, ...] = (), **_kw: object
    ):
        # Mirrors the real send: images are validated while the message is built.
        "".join(qq_image_segment(image) for image in images)
        return {"message_id": "88"}

    adapter.send_target = AsyncMock(side_effect=build_message)
    message = _reply("902", media=[str(tmp_path / "missing.png")], chat_type="private")

    with pytest.raises(ValueError, match="QQ 图片文件不存在"):
        await adapter._on_response(message)

    assert _receipts(adapter) == [("failed", "", None)]
