"""accounts.delete follows the plugin plan and writes config via the plugin path."""

from __future__ import annotations

from typing import Any, cast

import pytest

from core.accounts import AccountDeletionPlan
from core.accounts.delivery_ledger import AccountDeliveryLedger
from core.roles.store import RoleStore
from desktop_bridge.runtime.account_deletion import RuntimeAccountDeletion
from desktop_bridge.runtime.apply import RuntimeApplyError
from desktop_bridge.runtime.plugin_config import RuntimePluginConfig
from session.manager import SessionManager


class _PluginConfig:
    def __init__(self, *, invalid: bool = False) -> None:
        self.invalid = invalid
        self.checks: list[tuple[str, dict[str, Any]]] = []
        self.writes: list[dict[str, Any]] = []

    def check_replacement(self, plugin_id, values):
        self.checks.append((plugin_id, values))
        if self.invalid:
            raise RuntimeApplyError("plugin_config_invalid", "bots 无效")

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


def _plan(steps: list[str], config: dict[str, Any] | None):
    def plan(config_ref: str) -> AccountDeletionPlan:
        async def disconnect() -> None:
            steps.append(f"disconnect:{config_ref}")

        async def purge() -> None:
            steps.append(f"purge:{config_ref}")

        return AccountDeletionPlan(disconnect, purge, config)

    return plan


async def _delete(deletion: RuntimeAccountDeletion, payload: dict[str, Any]):
    return await deletion.delete(
        payload, prepare_service="prepare", publish_service="publish"
    )


@pytest.mark.asyncio
async def test_config_backed_credential_is_removed_through_plugin_config(tmp_path):
    roles, account_id = _roles_with_account(tmp_path)
    steps: list[str] = []
    roles.accounts.set_delete_handler("telegram", _plan(steps, {"bots": []}))
    plugin_config = _PluginConfig()
    deletion = RuntimeAccountDeletion(roles, cast(RuntimePluginConfig, plugin_config))

    result = await _delete(deletion, {"account_id": account_id, "role_id": "mira"})

    assert steps == ["disconnect:bot_a", "purge:bot_a"]
    assert plugin_config.checks == [("telegram", {"bots": []})]
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
async def test_rejected_plugin_config_leaves_connection_data_and_record(tmp_path):
    roles, account_id = _roles_with_account(tmp_path)
    steps: list[str] = []
    roles.accounts.set_delete_handler("telegram", _plan(steps, {"bots": "x"}))
    plugin_config = _PluginConfig(invalid=True)
    deletion = RuntimeAccountDeletion(roles, cast(RuntimePluginConfig, plugin_config))

    with pytest.raises(RuntimeApplyError, match="bots 无效"):
        await _delete(deletion, {"account_id": account_id, "role_id": "mira"})

    assert steps == []
    assert plugin_config.writes == []
    assert [row.record.id for row in RoleStore(tmp_path).accounts.list()] == [
        account_id
    ]


@pytest.mark.asyncio
async def test_plugin_private_cleanup_skips_config_and_requires_both_ids(tmp_path):
    roles, account_id = _roles_with_account(tmp_path)
    steps: list[str] = []
    roles.accounts.set_delete_handler("telegram", _plan(steps, None))
    plugin_config = _PluginConfig()
    deletion = RuntimeAccountDeletion(roles, cast(RuntimePluginConfig, plugin_config))
    with pytest.raises(RuntimeApplyError, match="不能为空"):
        await _delete(deletion, {"account_id": account_id})
    result = await _delete(deletion, {"account_id": account_id, "role_id": "mira"})
    assert result == {"account_id": account_id, "config": None}
    assert plugin_config.checks == plugin_config.writes == []
    assert roles.accounts.list() == []


@pytest.mark.asyncio
async def test_history_and_delivery_ledger_keep_the_deleted_account(tmp_path):
    roles, account_id = _roles_with_account(tmp_path)
    sessions = SessionManager(tmp_path)
    session = sessions.get_or_create("role:mira")
    session.add_message("user", "你好", metadata={"account_id": account_id})
    session.add_message(
        "assistant", "在的", metadata={"delivery_account_id": account_id}
    )
    sessions.save(session)
    ledger = AccountDeliveryLedger(tmp_path)
    attempt = ledger.begin(
        role_id="mira",
        account_id=account_id,
        target_kind="private",
        target_id="7",
        target_options={},
        source="proactive",
    )
    ledger.mark_sent(attempt.attempt_id, "m-1")
    roles.accounts.set_delete_handler("telegram", _plan([], None))
    deletion = RuntimeAccountDeletion(roles, cast(RuntimePluginConfig, _PluginConfig()))

    await _delete(deletion, {"account_id": account_id, "role_id": "mira"})

    assert roles.accounts.list() == []
    reloaded = SessionManager(tmp_path).get_or_create("role:mira")
    assert [message.get("metadata") for message in reloaded.messages] == [
        {"account_id": account_id},
        {"delivery_account_id": account_id},
    ]
    # Model context still renders both turns from the retained history.
    user, assistant = reloaded.get_history()
    assert user["content"].endswith("你好")
    assert assistant["content"] == "在的"
    [kept] = AccountDeliveryLedger(tmp_path).list_for_role("mira")
    assert (kept.account_id, kept.status, kept.platform_message_id) == (
        account_id,
        "sent",
        "m-1",
    )
