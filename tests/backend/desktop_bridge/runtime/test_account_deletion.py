"""accounts.delete runs plugin cleanup, writes config through the plugin path."""

from __future__ import annotations

from typing import Any, cast

import pytest

from core.accounts import AccountCleanup
from core.roles.store import RoleStore
from desktop_bridge.runtime.account_deletion import RuntimeAccountDeletion
from desktop_bridge.runtime.apply import RuntimeApplyError
from desktop_bridge.runtime.plugin_config import RuntimePluginConfig


class _PluginConfig:
    def __init__(self) -> None:
        self.writes: list[dict[str, Any]] = []

    async def replace_from_plugin(
        self, plugin_id, values, *, operation_id, prepare_service, publish_service
    ):
        assert (prepare_service, publish_service) == ("prepare", "publish")
        self.writes.append(
            {"plugin_id": plugin_id, "values": values, "operation_id": operation_id}
        )
        return {"plugin_id": plugin_id, "generation": 2}


def _roles_with_account(tmp_path) -> tuple[RoleStore, str]:
    roles = RoleStore(tmp_path)
    roles.create_role(name="Mira", system_prompt="mira", role_id="mira")
    roles.accounts.set_plugin_enabled("telegram", True)
    account = roles.accounts.register(
        plugin_id="telegram",
        platform="telegram",
        platform_account_id="42",
        config_ref="bot_a",
        token="t",
    )
    roles.accounts.assign(account.record.id, "mira")
    return roles, account.record.id


@pytest.mark.asyncio
async def test_config_backed_credential_is_removed_through_plugin_config(tmp_path):
    roles, account_id = _roles_with_account(tmp_path)
    cleaned: list[str] = []

    async def cleanup(config_ref: str) -> AccountCleanup:
        cleaned.append(config_ref)
        return AccountCleanup(plugin_config={"bots": []})

    roles.accounts.set_delete_handler("telegram", cleanup)
    plugin_config = _PluginConfig()
    deletion = RuntimeAccountDeletion(roles, cast(RuntimePluginConfig, plugin_config))

    result = await deletion.delete(
        {"account_id": account_id, "role_id": "mira"},
        prepare_service="prepare",
        publish_service="publish",
    )

    assert cleaned == ["bot_a"]
    [write] = plugin_config.writes
    assert (write["plugin_id"], write["values"]) == ("telegram", {"bots": []})
    assert write["operation_id"].startswith(f"account-delete:{account_id}:")
    assert result == {
        "account_id": account_id,
        "config": {"plugin_id": "telegram", "generation": 2},
    }
    assert roles.accounts.list(role_id="mira") == []
    assert RoleStore(tmp_path).accounts.list() == []


@pytest.mark.asyncio
async def test_plugin_private_cleanup_skips_config_and_requires_both_ids(tmp_path):
    roles, account_id = _roles_with_account(tmp_path)

    async def cleanup(config_ref: str) -> AccountCleanup:
        return AccountCleanup()

    roles.accounts.set_delete_handler("telegram", cleanup)
    plugin_config = _PluginConfig()
    deletion = RuntimeAccountDeletion(roles, cast(RuntimePluginConfig, plugin_config))
    with pytest.raises(RuntimeApplyError, match="不能为空"):
        await deletion.delete(
            {"account_id": account_id},
            prepare_service="prepare",
            publish_service="publish",
        )
    result = await deletion.delete(
        {"account_id": account_id, "role_id": "mira"},
        prepare_service="prepare",
        publish_service="publish",
    )
    assert result == {"account_id": account_id, "config": None}
    assert plugin_config.writes == []
    assert roles.accounts.list() == []
