from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

import plugins.qq.backend.accounts_inbound_adapter as inbound_adapter
from plugins.qq.backend.accounts_inbound import inbound_message
from plugins.qq.backend.accounts_inbound_adapter import QQInboundAdapter
from plugins.qq.backend.accounts_group_names import QQGroupNames
from plugins.qq.backend.accounts_store import QQConnectionConfig
from plugins.qq.backend.onebot import OneBotError
from websockets.exceptions import ConnectionClosed


def _actions(**actions: object) -> SimpleNamespace:
    """NapCat actions; a message without a reply segment never asks for a sender."""
    return SimpleNamespace(message_sender=AsyncMock(), **actions)


def _adapter() -> QQInboundAdapter:
    adapter = QQInboundAdapter()
    adapter._actions = _actions()
    return adapter


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
    adapter = _adapter()
    adapter._group_names = QQGroupNames(AsyncMock(return_value="读书会"))
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
    adapter = _adapter()
    adapter._group_names = QQGroupNames(AsyncMock(return_value="读书会"))
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
    adapter = _adapter()
    adapter._group_names = QQGroupNames(AsyncMock(return_value="读书会"))
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


def _private_message(content: str, **event: object):
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
            **event,
        },
    )
    assert message is not None
    return message


@pytest.mark.asyncio
async def test_private_pairing_code_binds_with_platform_scope_and_is_confirmed():
    adapter = _adapter()
    adapter._group_names = QQGroupNames(AsyncMock(return_value="读书会"))
    bus = SimpleNamespace(publish_inbound=AsyncMock())
    pairings = []

    class AccountRouter:
        def claim_pairing(self, message, *, scope):
            pairings.append((message.sender, message.content, scope))
            return message.content == "PAIR1234"

        def route_account_inbound(self, message):
            return message

    adapter._actions = _actions(send_target=AsyncMock(return_value={"message_id": "9"}))
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


@pytest.mark.asyncio
async def test_group_temporary_session_cannot_pair():
    adapter = _adapter()
    bus = SimpleNamespace(publish_inbound=AsyncMock())
    claim_pairing = Mock()
    adapter._actions = _actions(send_target=AsyncMock())
    adapter._ctx = SimpleNamespace(
        bus=bus,
        channel_hub=SimpleNamespace(
            claim_pairing=claim_pairing, route_account_inbound=lambda message: message
        ),
        http_resources=SimpleNamespace(),
        attachment_store=SimpleNamespace(),
    )

    await adapter._accept_inbound(
        _private_message("PAIR1234", sub_type="group", group_id=777)
    )

    claim_pairing.assert_not_called()
    adapter._actions.send_target.assert_not_awaited()
    [call] = bus.publish_inbound.await_args_list
    assert call.args[0].content == "PAIR1234"


@pytest.mark.asyncio
async def test_group_message_carries_the_group_name_to_the_host():
    adapter = _adapter()
    fetch = AsyncMock(return_value="读书会")
    adapter._group_names = QQGroupNames(fetch)
    bus = SimpleNamespace(publish_inbound=AsyncMock())
    routed = []
    adapter._ctx = SimpleNamespace(
        bus=bus,
        channel_hub=SimpleNamespace(
            claim_pairing=lambda *_args, **_kwargs: False,
            route_account_inbound=lambda message: routed.append(message) or message,
        ),
        http_resources=SimpleNamespace(),
        attachment_store=SimpleNamespace(),
    )

    await adapter._accept_inbound(_group_message(True))
    await adapter._accept_inbound(_group_message(True))

    assert [message.metadata["group_name"] for message in routed] == ["读书会"] * 2
    fetch.assert_awaited_once_with("account-b", "777")
    await adapter._accept_inbound(_private_message("你好"))
    assert "group_name" not in routed[-1].metadata


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure",
    [
        # ``_socket_for`` when the account has no live socket.
        OneBotError("QQ 账号不在线"),
        # ``OneBotSocket.call`` when the socket closes while sending.
        ConnectionClosed(None, None),
        TimeoutError(),
    ],
)
async def test_group_message_is_routed_without_a_name_when_lookup_fails(
    caplog, failure
):
    adapter = _adapter()
    adapter._group_names = QQGroupNames(AsyncMock(side_effect=failure))
    bus = SimpleNamespace(publish_inbound=AsyncMock())
    adapter._ctx = SimpleNamespace(
        bus=bus,
        channel_hub=SimpleNamespace(route_account_inbound=lambda message: message),
        http_resources=SimpleNamespace(),
        attachment_store=SimpleNamespace(),
    )

    await adapter._accept_inbound(_group_message(True))

    [call] = bus.publish_inbound.await_args_list
    assert "group_name" not in call.args[0].metadata
    assert "名称查询失败" in caplog.text


@pytest.mark.asyncio
async def test_group_reply_target_reaches_the_host_and_leaves_the_text():
    adapter = _adapter()
    adapter._group_names = QQGroupNames(AsyncMock(return_value="读书会"))
    adapter._actions = SimpleNamespace(message_sender=AsyncMock(return_value="202"))
    bus = SimpleNamespace(publish_inbound=AsyncMock())
    routed = []
    adapter._ctx = SimpleNamespace(
        bus=bus,
        channel_hub=SimpleNamespace(
            route_account_inbound=lambda message: routed.append(message) or message
        ),
        http_resources=SimpleNamespace(),
        attachment_store=SimpleNamespace(),
    )

    message = _group_message(False)
    message.content = "[CQ:reply,id=-35] 是这样吗"
    await adapter._accept_inbound(message)

    adapter._actions.message_sender.assert_awaited_once_with("account-b", "-35")
    assert routed[0].metadata["reply_to_sender_id"] == "202"
    # The host is handed the cleaned text: what it keeps for a turn or for
    # the group's listening records (#538) carries no CQ codes.
    assert routed[0].content == "是这样吗"
    [call] = bus.publish_inbound.await_args_list
    assert call.args[0].content == "是这样吗"


@pytest.mark.asyncio
async def test_received_message_refreshes_its_sender_and_group_avatars():
    adapter = _adapter()
    adapter._avatars = Mock(refresh=Mock(return_value=None))
    adapter._group_names = QQGroupNames(AsyncMock(return_value="读书会"))
    adapter._ctx = SimpleNamespace(
        bus=SimpleNamespace(publish_inbound=AsyncMock()),
        channel_hub=SimpleNamespace(route_account_inbound=lambda message: message),
        http_resources=SimpleNamespace(),
        attachment_store=SimpleNamespace(),
    )

    await adapter._accept_inbound(_group_message(True))

    assert {call.args[:3] for call in adapter._avatars.refresh.call_args_list} == {
        ("sender", "qq", "902"),
        ("chat", "qq", "gqq:777"),
    }
