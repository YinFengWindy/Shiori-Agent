"""Desktop account commands read the index and delegate changes to the owning plugin."""

from __future__ import annotations

import pytest

from core.accounts import (
    AccountDeletionPlan,
    AccountNotFoundError,
    AccountRegistry,
    AccountResponseRules,
)
from desktop_bridge.account_requests import DesktopAccountRequestHandler


def _registry() -> tuple[AccountRegistry, str]:
    accounts = AccountRegistry({"role"}.__contains__)
    account = accounts.register(
        plugin_id="demo",
        platform="demo",
        platform_account_id="101",
        config_ref="private-key",
        token="running",
        role_id="role",
        display_name="Demo",
    )
    return accounts, account.record.id


@pytest.mark.asyncio
async def test_list_and_detail_use_live_account_snapshot():
    accounts, account_id = _registry()
    accounts.report(
        account_id, "running", connection="online", capabilities=frozenset({"groups"})
    )
    handler = DesktopAccountRequestHandler(accounts)
    detail = await handler.handle("accounts.get", {"account_id": account_id})
    assert detail == {
        "account": {
            "id": "demo:101",
            "plugin_id": "demo",
            "platform": "demo",
            "platform_account_id": "101",
            "config_ref": "private-key",
            "display_name": "Demo",
            "avatar_url": "",
            "role_id": "role",
            "runtime_active": True,
            "connection": "online",
            "capabilities": ["groups"],
            "error": "",
            "response_rules": {
                "private_enabled": True,
                "group_enabled": True,
                "require_mention": True,
                "blocked_sender_ids": [],
                "group_rules": [],
            },
        }
    }
    assert await handler.handle("accounts.list", {"role_id": "role"}) == {
        "accounts": [detail["account"]]
    }
    assert await handler.handle("accounts.list", {"role_id": "other"}) == {
        "accounts": []
    }


@pytest.mark.asyncio
async def test_rules_are_validated_then_saved_by_the_plugin():
    accounts, account_id = _registry()
    saved: list[AccountResponseRules] = []
    accounts.set_rules_handler("demo", lambda _ref, rules: saved.append(rules))
    handler = DesktopAccountRequestHandler(accounts)
    rules = {
        "private_enabled": False,
        "group_enabled": True,
        "require_mention": True,
        "blocked_sender_ids": [" member-1 "],
        "group_rules": [],
    }
    with pytest.raises(ValueError, match="Invalid account response rules"):
        await handler.handle(
            "accounts.rules.set",
            {
                "account_id": account_id,
                "response_rules": {**rules, "group_enabled": "no"},
            },
        )
    assert saved == []
    changed = await handler.handle(
        "accounts.rules.set", {"account_id": account_id, "response_rules": rules}
    )
    assert changed is not None
    assert changed["account"]["response_rules"]["blocked_sender_ids"] == ["member-1"]
    assert saved == [
        AccountResponseRules(private_enabled=False, blocked_sender_ids=("member-1",))
    ]


@pytest.mark.asyncio
async def test_delete_runs_the_plugin_cleanup_and_drops_the_account():
    accounts, account_id = _registry()
    purged: list[str] = []

    def plan(config_ref: str) -> AccountDeletionPlan:
        async def disconnect() -> None:
            return None

        async def purge() -> None:
            purged.append(config_ref)

        return AccountDeletionPlan(disconnect, purge)

    accounts.set_delete_handler("demo", plan)
    handler = DesktopAccountRequestHandler(accounts)
    with pytest.raises(ValueError, match="不能为空"):
        await handler.handle("accounts.delete", {"account_id": account_id})
    assert await handler.handle(
        "accounts.delete", {"account_id": account_id, "role_id": "role"}
    ) == {"account_id": account_id}
    assert purged == ["private-key"]
    with pytest.raises(AccountNotFoundError):
        await handler.handle("accounts.get", {"account_id": account_id})
