"""QQ role replies: group replies @ their trigger; receipts carry the snapshot."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from bus.events import OutboundMessage
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


def _reply(chat_id: str, **metadata: object) -> OutboundMessage:
    return OutboundMessage(
        channel="qq",
        chat_id=chat_id,
        content="好",
        metadata={"account_id": "qq:101", "sender_id": "902", **metadata},
        committed_message_id="committed",
    )


@pytest.mark.asyncio
async def test_group_reply_mentions_trigger_then_chosen_members() -> None:
    adapter = _Adapter()
    message = _reply("gqq:777", chat_type="group", mention_ids=["903", "902"])

    await adapter._on_response(message)

    adapter.send_target.assert_awaited_once_with(
        "qq:101", "group", "777", "好", mention_ids=("902", "903")
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
        "qq:101", "private", "902", "好", mention_ids=()
    )
