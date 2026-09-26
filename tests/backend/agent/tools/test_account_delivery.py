"""Account tools honor the current role, plugin state, and platform receipt."""

from __future__ import annotations

import json
from typing import Any

import pytest

from agent.tools.account_delivery import (
    AccountDelivery,
    AccountSendTool,
    account_delivery_scope,
)
from core.accounts import AccountRegistry


class _Rpc:
    def __init__(self, plugin_id: str = "qq") -> None:
        self.plugin_id = plugin_id
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def resolve(self, name: str):
        async def handle(payload: dict[str, Any]):
            self.calls.append((name, payload))
            if name.endswith("account.targets"):
                return {"items": [{"id": "42"}], "complete": True}
            return {"message_id": "receipt-9"}

        return (self.plugin_id, handle)


@pytest.mark.asyncio
async def test_account_send_requires_live_owner_and_returns_receipt(tmp_path) -> None:
    accounts = AccountRegistry(tmp_path, lambda role_id: role_id in {"mira", "other"})
    accounts.set_plugin_enabled("qq", True)
    account = accounts.register(
        plugin_id="qq",
        platform="qq",
        platform_account_id="100",
        config_ref="one",
        token="live",
    )
    account_id = account.record.id
    accounts.assign(account_id, "mira")
    accounts.report(
        account_id,
        "live",
        connection="online",
        capabilities=frozenset({"friends", "send"}),
    )
    rpc = _Rpc()
    delivery = AccountDelivery(accounts, rpc)
    assert json.loads(delivery.list_accounts("mira"))[0]["online"]
    assert json.loads(
        await delivery.targets(account_id, "mira", "friends", "", "")
    ) == {
        "items": [{"id": "42"}],
        "complete": True,
    }
    state: dict[str, bool] = {}
    with account_delivery_scope(state):
        receipt = json.loads(
            await AccountSendTool(delivery).execute(
                account_id=account_id,
                role_id="mira",
                target_kind="private",
                target_id="42",
                message="hello",
            )
        )
    assert receipt["platform_message_id"] == "receipt-9"
    assert rpc.calls[-1][1]["target_id"] == "42"
    assert rpc.calls[-1][0] == "plugin.qq.account.send"
    assert state == {"sent": True}
    with pytest.raises(PermissionError):
        await delivery.send(account_id, "other", "private", "42", "hello", None)
    accounts.set_plugin_enabled("qq", False)
    with pytest.raises(PermissionError):
        await delivery.send(account_id, "mira", "private", "42", "hello", None)
    assert len(rpc.calls) == 2


@pytest.mark.asyncio
async def test_uniform_contract_accepts_unrecognized_plugin_without_host_mapping(
    tmp_path,
) -> None:
    accounts = AccountRegistry(tmp_path, lambda role_id: role_id == "mira")
    accounts.set_plugin_enabled("new_plugin", True)
    account = accounts.register(
        plugin_id="new_plugin",
        platform="new_platform",
        platform_account_id="identity",
        config_ref="private-ref",
        token="live",
    )
    account_id = account.record.id
    accounts.assign(account_id, "mira")
    accounts.report(account_id, "live", connection="online")
    rpc = _Rpc("new_plugin")
    delivery = AccountDelivery(accounts, rpc)

    await delivery.targets(account_id, "mira", "custom", "parent", "member")
    await delivery.send(account_id, "mira", "custom", "opaque", "hello", None)
    assert rpc.calls == [
        (
            "plugin.new_plugin.account.targets",
            {
                "account_id": account_id,
                "kind": "custom",
                "group_id": "parent",
                "member_id": "member",
            },
        ),
        (
            "plugin.new_plugin.account.send",
            {
                "account_id": account_id,
                "target_kind": "custom",
                "target_id": "opaque",
                "message": "hello",
                "message_thread_id": None,
            },
        ),
    ]
