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
