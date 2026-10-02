"""QQ role replies: group replies @ their trigger; receipts carry the snapshot."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from shiori_sdk.messages import OutboundMessage
from plugins.qq.backend.accounts_actions import qq_image_segment
from plugins.qq.backend.accounts_outbound_adapter import QQOutboundAdapter

_VIA = {
    "platform": "qq",
    "platform_account_id": "101",
    "display_name": "小栞",
    "prefix": "QQ 号「小栞」（101）",
}


class _Adapter(QQOutboundAdapter):
    def __init__(self) -> None:
        self._sockets = {}
        self._ctx = SimpleNamespace(channel_hub=Mock())
        self.send_target = AsyncMock(return_value={"message_id": "88"})

    def via_account(self, account_id: str) -> dict[str, str]:
        assert account_id == "qq:101"
        return _VIA


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
async def test_group_reply_mentions_trigger_then_chosen_members() -> None:
    adapter = _Adapter()
    message = _reply("gqq:777", chat_type="group", mention_ids=["903", "902"])

    await adapter._on_response(message)

    adapter.send_target.assert_awaited_once_with(
        "qq:101", "group", "777", "好", mention_ids=("902", "903"), images=()
    )
    adapter._ctx.channel_hub.mark_delivery.assert_called_once_with(
        message,
        default_channel="qq",
        delivery_status="sent",
        external_message_id="88",
        via_account=_VIA,
    )


@pytest.mark.asyncio
async def test_private_reply_mentions_nobody() -> None:
    adapter = _Adapter()

    await adapter._on_response(_reply("902", chat_type="private", mention_ids=["9"]))

    adapter.send_target.assert_awaited_once_with(
        "qq:101", "private", "902", "好", mention_ids=(), images=()
    )


@pytest.mark.asyncio
async def test_group_reply_skips_unusable_chosen_mentions_and_still_sends(
    caplog: pytest.LogCaptureFixture,
) -> None:
    adapter = _Adapter()
    message = _reply("gqq:777", chat_type="group", mention_ids=["小明", "903"])

    with caplog.at_level("WARNING"):
        await adapter._on_response(message)

    adapter.send_target.assert_awaited_once_with(
        "qq:101", "group", "777", "好", mention_ids=("902", "903"), images=()
    )
    assert (
        adapter._ctx.channel_hub.mark_delivery.call_args.kwargs["delivery_status"]
        == "sent"
    )
    assert "小明" in caplog.text


@pytest.mark.asyncio
async def test_private_reply_sends_its_images_with_the_text() -> None:
    adapter = _Adapter()

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
async def test_group_reply_sends_images_and_keeps_mentions() -> None:
    adapter = _Adapter()
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
    adapter._ctx.channel_hub.mark_delivery.assert_called_once_with(
        message,
        default_channel="qq",
        delivery_status="sent",
        external_message_id="88",
        via_account=_VIA,
    )


@pytest.mark.asyncio
async def test_image_only_reply_is_sent() -> None:
    adapter = _Adapter()

    await adapter._on_response(
        _reply("902", content="", media=["/cg/a.png"], chat_type="private")
    )

    adapter.send_target.assert_awaited_once_with(
        "qq:101", "private", "902", "", mention_ids=(), images=("/cg/a.png",)
    )
    assert (
        adapter._ctx.channel_hub.mark_delivery.call_args.kwargs["delivery_status"]
        == "sent"
    )


@pytest.mark.asyncio
async def test_invalid_local_image_marks_the_reply_failed(tmp_path: Path) -> None:
    adapter = _Adapter()

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

    adapter._ctx.channel_hub.mark_delivery.assert_called_once_with(
        message,
        default_channel="qq",
        delivery_status="failed",
        external_message_id="",
        via_account=None,
    )
