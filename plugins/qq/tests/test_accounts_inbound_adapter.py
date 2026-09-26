from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from plugins.qq.backend.accounts_inbound import inbound_message
from plugins.qq.backend.accounts_inbound_adapter import QQInboundAdapter


def _group_message(mentioned: bool):
    raw = "[CQ:at,qq=202] hello" if mentioned else "hello"
    message = inbound_message(
        account_id="account-b",
        expected_uin="202",
        event={
            "post_type": "message",
            "message_type": "group",
            "self_id": 202,
            "group_id": 777,
            "user_id": 902,
            "raw_message": raw,
        },
    )
    assert message is not None
    return message


@pytest.mark.asyncio
async def test_legacy_group_admission_preserves_default_mention_trigger():
    adapter = QQInboundAdapter()
    bus = SimpleNamespace(publish_inbound=AsyncMock())
    hub = SimpleNamespace(
        is_sender_allowed=Mock(return_value=True),
        route_inbound=Mock(side_effect=lambda message: message),
    )
    adapter._ctx = SimpleNamespace(bus=bus, channel_hub=hub)
    await adapter._accept_inbound(_group_message(False))
    bus.publish_inbound.assert_not_awaited()
    hub.is_sender_allowed.assert_not_called()

    adapter._ctx = SimpleNamespace(
        bus=bus,
        channel_hub=hub,
        http_resources=SimpleNamespace(),
        attachment_store=SimpleNamespace(),
    )
    await adapter._accept_inbound(_group_message(True))
    sent = bus.publish_inbound.await_args.args[0]
    assert sent.content == "hello"
    assert sent.metadata["account_id"] == "account-b"
    hub.is_sender_allowed.assert_called_once()


@pytest.mark.asyncio
async def test_account_router_receives_unmentioned_group_before_host_policy():
    adapter = QQInboundAdapter()
    bus = SimpleNamespace(publish_inbound=AsyncMock())
    routed = []

    class AccountRouter:
        def route_account_inbound(self, message):
            routed.append(message)
            return message

    adapter._ctx = SimpleNamespace(
        bus=bus,
        channel_hub=AccountRouter(),
        http_resources=SimpleNamespace(),
        attachment_store=SimpleNamespace(),
    )
    await adapter._accept_inbound(_group_message(False))
    assert len(routed) == 1
    assert routed[0].metadata["mentioned"] is False
    assert bus.publish_inbound.await_count == 1


@pytest.mark.asyncio
async def test_account_router_can_reject_unmentioned_group():
    adapter = QQInboundAdapter()
    bus = SimpleNamespace(publish_inbound=AsyncMock())

    class AccountRouter:
        def route_account_inbound(self, message):
            assert message.metadata["mentioned"] is False
            return None

    adapter._ctx = SimpleNamespace(
        bus=bus,
        channel_hub=AccountRouter(),
        http_resources=SimpleNamespace(),
        attachment_store=SimpleNamespace(),
    )
    await adapter._accept_inbound(_group_message(False))
    bus.publish_inbound.assert_not_awaited()
