from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import plugins.qq.backend.accounts_inbound_adapter as inbound_adapter
from plugins.qq.backend.accounts_inbound import inbound_message
from plugins.qq.backend.accounts_inbound_adapter import QQInboundAdapter
from plugins.qq.backend.accounts_store import QQConnectionConfig


def _group_message(mentioned: bool):
    raw = "[CQ:at,qq=202] hello" if mentioned else "hello"
    message = inbound_message(
        account_id="account-b",
        expected_uin="202",
        via_account=QQConnectionConfig(
            ref="b", ws_uri="ws://127.0.0.1:1", ws_token="t", expected_uin="202"
        ).via_account(),
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


@pytest.mark.asyncio
async def test_account_router_rejection_fetches_no_image(monkeypatch):
    adapter = QQInboundAdapter()
    bus = SimpleNamespace(publish_inbound=AsyncMock())
    download = AsyncMock()
    monkeypatch.setattr(inbound_adapter, "download_to_temp", download)

    class AccountRouter:
        def route_account_inbound(self, message):
            assert message.metadata["account_id"] == "account-b"
            assert message.metadata["mentioned"] is False
            return None

    adapter._ctx = SimpleNamespace(
        bus=bus,
        channel_hub=AccountRouter(),
        http_resources=SimpleNamespace(),
        attachment_store=SimpleNamespace(),
    )
    message = _group_message(False)
    message.content = "[CQ:image,url=https://example.com/private.png]"
    await adapter._accept_inbound(message)
    download.assert_not_awaited()
    bus.publish_inbound.assert_not_awaited()


def _private_message(content: str):
    message = inbound_message(
        account_id="account-b",
        expected_uin="202",
        via_account=QQConnectionConfig(
            ref="b", ws_uri="ws://127.0.0.1:1", ws_token="t", expected_uin="202"
        ).via_account(),
        event={
            "post_type": "message",
            "message_type": "private",
            "self_id": 202,
            "user_id": 902,
            "raw_message": content,
        },
    )
    assert message is not None
    return message


@pytest.mark.asyncio
async def test_private_pairing_code_binds_with_platform_scope_and_is_confirmed():
    adapter = QQInboundAdapter()
    bus = SimpleNamespace(publish_inbound=AsyncMock())
    pairings = []

    class AccountRouter:
        def claim_pairing(self, message, *, scope):
            pairings.append((message.sender, message.content, scope))
            return message.content == "PAIR1234"

        def route_account_inbound(self, message):
            return message

    adapter._actions = SimpleNamespace(
        send_target=AsyncMock(return_value={"message_id": "9"})
    )
    adapter._ctx = SimpleNamespace(
        bus=bus,
        channel_hub=AccountRouter(),
        http_resources=SimpleNamespace(),
        attachment_store=SimpleNamespace(),
    )
    await adapter._accept_inbound(_private_message("PAIR1234"))
    await adapter._accept_inbound(_private_message("你好"))
    # A group message is never offered as a pairing code.
    await adapter._accept_inbound(_group_message(True))

    assert pairings == [("902", "PAIR1234", "platform"), ("902", "你好", "platform")]
    adapter._actions.send_target.assert_awaited_once_with(
        "account-b", "private", "902", "已绑定"
    )
    assert [call.args[0].content for call in bus.publish_inbound.await_args_list] == [
        "你好",
        "hello",
    ]
