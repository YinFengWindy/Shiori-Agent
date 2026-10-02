from __future__ import annotations


from unittest.mock import AsyncMock

import pytest

from core.accounts.target_contract import AccountTarget, UncertainDeliveryError
from agent.account_delivery import AccountDelivery
from core.accounts import AccountRegistry
from core.accounts.delivery_ledger import AccountDeliveryLedger
from plugins.qq.backend.accounts_actions import (
    QQAccountActions,
)
from plugins.qq.backend.onebot import OneBotDisconnected, OneBotError
from core.identity import UserIdentityStore


def _SENDER(account_id: str) -> tuple[str, str]:
    return "101", "米拉"


@pytest.mark.asyncio
async def test_disconnect_is_pending_but_onebot_rejection_is_failed(tmp_path):
    accounts = AccountRegistry(lambda role_id: role_id == "mira")
    account = accounts.register(
        plugin_id="qq",
        platform="qq",
        platform_account_id="101",
        config_ref="bot",
        token="live",
        role_id="mira",
    )
    account_id = account.record.id
    accounts.report(account_id, "live", connection="online")
    socket = AsyncMock()
    actions = QQAccountActions(lambda selected: socket, AsyncMock(), _SENDER)

    async def send(payload):
        return await actions.send_target(
            payload["account_id"],
            payload["target_kind"],
            payload["target_id"],
            payload["message"],
        )

    target = AccountTarget("private", "901")

    rpc = type("Rpc", (), {"resolve": lambda self, name: ("qq", send)})()
    ledger = AccountDeliveryLedger(tmp_path)
    delivery = AccountDelivery(accounts, rpc, ledger, UserIdentityStore(tmp_path))
    socket.call.side_effect = OneBotDisconnected("NapCat WebSocket 已断开")
    with pytest.raises(UncertainDeliveryError):
        await delivery.send("qq", "mira", target, "hi")
    socket.call.side_effect = OneBotError("NapCat send_private_msg 失败: denied")
    with pytest.raises(OneBotError, match="denied"):
        await delivery.send("qq", "mira", target, "hi")

    attempts = AccountDeliveryLedger(tmp_path).list_for_role("mira")
    assert [(row.status, row.error) for row in attempts] == [
        ("pending", "UncertainDeliveryError"),
        ("failed", "OneBotError"),
    ]
