"""The plugin runtime fixture shares account state with its desktop bridge."""

from __future__ import annotations

from pathlib import Path

import pytest

from desktop_bridge.runtime.service import ReloadableDesktopService
from shiori_plugin_testkit.bridge import plugin_bridge_request


@pytest.mark.asyncio
async def test_plugin_account_report_and_bridge_assignment_share_role_store(
    plugin_runtime, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    package = tmp_path / "account_demo"
    (package / "backend").mkdir(parents=True)
    (package / "manifest.yaml").write_text(
        "api: 2\nid: account_demo\ncapabilities: [accounts]\n",
        encoding="utf-8",
    )
    (package / "backend/plugin.py").write_text(
        "async def setup(ctx):\n"
        "    account = ctx.accounts.register(platform='demo', "
        "platform_account_id='101', config_ref='private', display_name='Old', "
        "avatar_url='https://example.test/old.png')\n"
        "    account = ctx.accounts.register(platform='demo', "
        "platform_account_id='101', config_ref='private', display_name='', "
        "avatar_url='')\n"
        "    ctx.accounts.report(account.record.id, connection='online', "
        "capabilities=frozenset({'contacts'}))\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "shiori_plugin_testkit.pytest_plugin.plugin_directory",
        lambda _plugin_id: package,
    )

    async with plugin_runtime(("account_demo",)) as (bridge, _config_path):
        assert isinstance(bridge, ReloadableDesktopService)
        core = bridge.app.core
        assert core is not None
        runtime_store = core.role_runtime_registry.repository.store
        assert bridge.roles is runtime_store

        listed = await plugin_bridge_request(bridge, "accounts.list")
        assert listed.error is None, listed.error
        assert len(listed.payload["accounts"]) == 1
        account = listed.payload["accounts"][0]
        assert account["plugin_enabled"] is True
        assert account["runtime_active"] is True
        assert account["connection"] == "online"
        assert account["capabilities"] == ["contacts"]
        assert account["display_name"] == ""
        assert account["avatar_url"] == ""

        created = await plugin_bridge_request(
            bridge, "roles.create", {"name": "Owner", "system_prompt": "Owner"}
        )
        assert created.error is None, created.error
        role_id = created.payload["role"]["id"]
        assigned = await plugin_bridge_request(
            bridge,
            "accounts.assign",
            {"account_id": account["id"], "role_id": role_id},
        )
        assert assigned.error is None, assigned.error
        assert assigned.payload["account"]["role_id"] == role_id
        assert runtime_store.accounts.get(account["id"]).record.role_id == role_id
        assert runtime_store.accounts.validate_access(
            runtime_store.accounts.authorize(account["id"], role_id)
        )
