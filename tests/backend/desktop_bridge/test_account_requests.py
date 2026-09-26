"""Desktop account reads use the same snapshots as runtime authorization."""

from __future__ import annotations

import pytest

from core.accounts import AccountRegistry
from desktop_bridge.account_requests import DesktopAccountRequestHandler


@pytest.mark.asyncio
async def test_list_and_assignment_use_live_account_snapshot(tmp_path):
    accounts = AccountRegistry(tmp_path, lambda role_id: role_id == "role")
    accounts.set_plugin_enabled("demo", True)
    account = accounts.register(
        plugin_id="demo",
        platform="demo",
        platform_account_id="101",
        config_ref="private-key",
        token="running",
        display_name="Demo",
    )
    accounts.report(
        account.record.id,
        "running",
        connection="online",
        capabilities=frozenset({"contacts"}),
    )
    handler = DesktopAccountRequestHandler(accounts)
    assigned = await handler.handle(
        "accounts.assign", {"account_id": account.record.id, "role_id": "role"}
    )
    assert assigned is not None
    assert assigned["account"]["role_id"] == "role"
    assert assigned["account"]["plugin_enabled"]
    assert assigned["account"]["runtime_active"]
    assert assigned["account"]["connection"] == "online"
    assert assigned["account"]["capabilities"] == ["contacts"]
    assert assigned["account"]["response_rules"] == {
        "private_enabled": True,
        "group_enabled": True,
        "require_mention": True,
        "blocked_sender_ids": [],
        "group_rules": [],
    }
    assert accounts.validate_access(accounts.authorize(account.record.id, "role"))

    listed = await handler.handle("accounts.list", {"role_id": "role"})
    assert listed == {"accounts": [assigned["account"]]}
    accounts.unregister(account.record.id, "running")
    detail = await handler.handle("accounts.get", {"account_id": account.record.id})
    assert detail is not None
    assert detail["account"]["plugin_enabled"]
    assert not detail["account"]["runtime_active"]
    assert detail["account"]["connection"] == "unknown"

    with pytest.raises(KeyError):
        await handler.handle(
            "accounts.assign", {"account_id": account.record.id, "role_id": "missing"}
        )
    assert (await handler.handle("accounts.assign", {"account_id": account.record.id}))[
        "account"
    ]["role_id"] is None


@pytest.mark.asyncio
async def test_rules_are_account_scoped_and_survive_reassignment_and_reload(tmp_path):
    accounts = AccountRegistry(tmp_path, lambda role_id: role_id in {"first", "second"})
    one = accounts.register(
        plugin_id="demo",
        platform="demo",
        platform_account_id="101",
        config_ref="one",
        token="one",
    )
    two = accounts.register(
        plugin_id="demo",
        platform="demo",
        platform_account_id="102",
        config_ref="two",
        token="two",
    )
    handler = DesktopAccountRequestHandler(accounts)
    rules = {
        "private_enabled": False,
        "group_enabled": False,
        "require_mention": False,
        "blocked_sender_ids": ["member-1", "member-1", " member-2 "],
        "group_rules": [
            {
                "chat_id": "group-7",
                "enabled": False,
                "require_mention": True,
                "blocked_sender_ids": ["group-member"],
            }
        ],
    }
    changed = await handler.handle(
        "accounts.rules.set",
        {
            "account_id": one.record.id,
            "response_rules": rules,
        },
    )
    assert changed is not None
    assert changed["account"]["response_rules"]["blocked_sender_ids"] == [
        "member-1",
        "member-2",
    ]
    await handler.handle(
        "accounts.assign",
        {
            "account_id": one.record.id,
            "role_id": "first",
        },
    )
    await handler.handle(
        "accounts.assign",
        {
            "account_id": one.record.id,
            "role_id": "second",
        },
    )
    restored = DesktopAccountRequestHandler(
        AccountRegistry(tmp_path, lambda role_id: role_id in {"first", "second"})
    )
    detail = await restored.handle("accounts.get", {"account_id": one.record.id})
    other = await restored.handle("accounts.get", {"account_id": two.record.id})
    assert detail is not None and other is not None
    assert detail["account"]["role_id"] == "second"
    assert detail["account"]["response_rules"]["group_enabled"] is False
    assert detail["account"]["response_rules"]["blocked_sender_ids"] == [
        "member-1",
        "member-2",
    ]
    assert detail["account"]["response_rules"]["group_rules"][0] == {
        "chat_id": "group-7",
        "enabled": False,
        "require_mention": True,
        "blocked_sender_ids": ["group-member"],
    }
    assert other["account"]["response_rules"]["group_enabled"] is True
    with pytest.raises(ValueError, match="Invalid account response rules"):
        await restored.handle(
            "accounts.rules.set",
            {
                "account_id": one.record.id,
                "response_rules": {**rules, "group_enabled": "false"},
            },
        )
