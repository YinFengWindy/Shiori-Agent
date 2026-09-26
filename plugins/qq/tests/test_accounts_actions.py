from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from core.accounts.target_contract import UncertainDeliveryError
from agent.account_delivery import AccountDelivery
from core.accounts import AccountRegistry
from core.accounts.delivery_ledger import AccountDeliveryLedger
from plugins.qq.backend.accounts_actions import QQAccountActions, qq_chat_target
from plugins.qq.backend.onebot import OneBotDisconnected, OneBotError


@pytest.mark.asyncio
async def test_actions_query_fresh_lists_and_require_actual_send_receipt():
    socket = AsyncMock()
    actions = QQAccountActions(lambda account_id: socket, AsyncMock())
    socket.call.return_value = [{"user_id": 902, "card": "群名片", "nickname": "昵称"}]
    result = await actions.discover("account-a", "members", "777")
    assert result == {
        "items": [{"id": "902", "name": "群名片"}],
        "complete": True,
        "source": "napcat",
    }
    socket.call.assert_awaited_with("get_group_member_list", {"group_id": 777})

    socket.call.return_value = {"message_id": 88}
    assert await actions.send_target("account-a", "private", "902", "hi") == {
        "message_id": "88"
    }
    socket.call.assert_awaited_with(
        "send_private_msg", {"user_id": 902, "message": "hi"}
    )

    socket.call.return_value = {}
    with pytest.raises(UncertainDeliveryError, match="有效回执"):
        await actions.send_target("account-a", "private", "902", "hi")
    socket.call.return_value = {"message_id": 89}
    with pytest.raises(ValueError, match="目标 ID"):
        await actions.send_target("account-a", "group", "gqq:777", "hi")


@pytest.mark.asyncio
async def test_actions_reject_invalid_directory_shape_and_propagate_api_failure():
    socket = AsyncMock()
    actions = QQAccountActions(lambda account_id: socket, AsyncMock())
    socket.call.return_value = {"items": []}
    with pytest.raises(OneBotError, match="无效列表"):
        await actions.discover("account-a", "friends")
    socket.call.side_effect = OneBotError("NapCat get_group_list 失败")
    with pytest.raises(OneBotError, match="get_group_list"):
        await actions.discover("account-a", "groups")


@pytest.mark.asyncio
async def test_disconnect_is_pending_but_onebot_rejection_is_failed(tmp_path):
    accounts = AccountRegistry(tmp_path, lambda role_id: role_id == "mira")
    accounts.set_plugin_enabled("qq", True)
    account = accounts.register(
        plugin_id="qq",
        platform="qq",
        platform_account_id="101",
        config_ref="bot",
        token="live",
    )
    account_id = account.record.id
    accounts.assign(account_id, "mira")
    accounts.report(account_id, "live", connection="online")
    socket = AsyncMock()
    actions = QQAccountActions(lambda selected: socket, AsyncMock())

    async def send(payload):
        return await actions.send_target(
            payload["account_id"],
            payload["target_kind"],
            payload["target_id"],
            payload["message"],
        )

    rpc = type("Rpc", (), {"resolve": lambda self, name: ("qq", send)})()
    ledger = AccountDeliveryLedger(tmp_path)
    delivery = AccountDelivery(accounts, rpc, ledger)
    socket.call.side_effect = OneBotDisconnected("NapCat WebSocket 已断开")
    with pytest.raises(UncertainDeliveryError):
        await delivery.send(account_id, "mira", "private", "901", "hi", None)
    socket.call.side_effect = OneBotError("NapCat send_private_msg 失败: denied")
    with pytest.raises(OneBotError, match="denied"):
        await delivery.send(account_id, "mira", "private", "901", "hi", None)

    attempts = AccountDeliveryLedger(tmp_path).list_for_role("mira")
    assert [(row.status, row.error) for row in attempts] == [
        ("pending", "UncertainDeliveryError"),
        ("failed", "OneBotError"),
    ]


def test_chat_target_preserves_qq_private_and_group_namespaces():
    assert qq_chat_target("901") == ("private", "901")
    assert qq_chat_target("gqq:777") == ("group", "777")
    with pytest.raises(ValueError, match="群号"):
        qq_chat_target("gqq:bad")
