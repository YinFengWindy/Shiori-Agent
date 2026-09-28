from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from typing import Any

import pytest
from shiori_plugin_testkit.bridge import plugin_bridge_request
from shiori_plugin_testkit.packages import stage_plugin_package

from agent.plugin_host import HostServices, PluginKernel, load_manifest
from bus.event_bus import EventBus
from core.accounts import AccountResponseRules
from core.roles.store import RoleStore
from plugins.qq.backend.channel.formatting import GROUP_PREFIX
from plugins.qq.backend.accounts_store import QQAccountsStore, QQConnectionConfig
from plugins.qq.backend.napcat_account_files import NapCatAccountFiles
from plugins.qq.backend.plugin import _cancel, _send_account

PLUGIN_DIR = Path(__file__).resolve().parents[1]


def _load_qq_channels(
    plugin_configs: dict[str, dict[str, Any]] | None = None,
) -> list[Any]:
    with tempfile.TemporaryDirectory() as tmp:
        plugin_dir = Path(tmp) / "qq"
        stage_plugin_package(PLUGIN_DIR, plugin_dir)
        workspace = Path(tmp) / "workspace"
        workspace.mkdir()
        kernel = PluginKernel(
            [Path(tmp)],
            services=HostServices(
                event_bus=EventBus(),
                plugin_configs=plugin_configs or {},
                workspace=workspace,
                role_store=RoleStore(workspace),
            ),
        )
        asyncio.run(kernel.load_all())
        assert kernel.loaded_count == 1
        return kernel.channels


def test_manifest_preserves_historical_channel_name() -> None:
    # Historical conversation keys retain the original QQ channel name.
    manifest = load_manifest(PLUGIN_DIR)
    assert manifest is not None
    assert manifest.id == "qq"
    assert manifest.display_name == "QQ（NapCat）"
    assert set(manifest.capabilities) == {
        "channels",
        "accounts",
        "workspace",
        "rpc",
    }
    assert manifest.config_model is None
    assert [item.name for item in manifest.channels] == ["qq"]


def test_manifest_group_prefix_matches_the_transport_group_format() -> None:
    # Account intake and outbound target validation share the group prefix.
    manifest = load_manifest(PLUGIN_DIR)
    assert manifest is not None
    types = {item.type: item.prefix for item in manifest.channels[0].chat_types}
    assert types == {"private": None, "group": GROUP_PREFIX}


def test_plugin_contributes_one_account_channel() -> None:
    [channel] = _load_qq_channels()
    assert channel.name == "qq"
    assert channel.configuration_key[0] == "qq-accounts"


@pytest.mark.asyncio
async def test_shared_account_send_adapts_target_and_rejects_topic() -> None:
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    via = QQConnectionConfig(
        ref="a", ws_uri="ws://127.0.0.1:1", ws_token="t", expected_uin="101"
    ).via_account()
    runtime = SimpleNamespace(
        send_target=AsyncMock(return_value={"message_id": "9"}),
        via_account=lambda account_id: via,
    )
    payload = {
        "account_id": "account-1",
        "target_kind": "group",
        "target_id": "42",
        "message": "hello",
        "message_thread_id": None,
        "group_id": "",
        "mention_ids": ["902"],
    }
    assert await _send_account(runtime, payload) == {
        "message_id": "9",
        "via_account": via,
    }
    runtime.send_target.assert_awaited_once_with(
        "account-1", "group", "42", "hello", group_id="", mention_ids=("902",)
    )
    with pytest.raises(ValueError, match="话题"):
        await _send_account(runtime, {**payload, "message_thread_id": 7})


@pytest.mark.asyncio
async def test_temporary_login_cancel_forwards_role_to_runtime() -> None:
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    runtime = SimpleNamespace(cancel_login=AsyncMock())
    assert await _cancel(runtime, {"ref": "aa", "role_id": "mira"}) == {"ok": True}
    runtime.cancel_login.assert_awaited_once_with("aa", "mira")


@pytest.mark.asyncio
async def test_deleting_an_account_removes_credentials_napcat_data_and_record(
    plugin_runtime, tmp_path
) -> None:
    roles = RoleStore(tmp_path)
    for role_id in ("mira", "other"):
        roles.create_role(role_id=role_id, name=role_id, system_prompt="m")
    store = QQAccountsStore(tmp_path)
    store.save(
        {
            ref: QQConnectionConfig(
                ref,
                "ws://127.0.0.1:1",
                f"secret-{ref}",
                expected_uin=uin,
                auto_connect=False,
                verified=True,
                role_id=role_id,
            )
            for ref, uin, role_id in (("aa", "101", "mira"), ("bb", "202", "other"))
        }
    )
    napcat = NapCatAccountFiles(store.path.parent / "managed-napcat")
    login = napcat.account_dir("aa") / "profile/AppData/Roaming/Tencent/QQNT"
    login.mkdir(parents=True)
    (login / "session.db").write_text("login", encoding="utf-8")
    async with plugin_runtime(("qq",)) as (service, path):
        config_before = path.read_text(encoding="utf-8")
        listed = await plugin_bridge_request(service, "accounts.list")
        accounts = {row["config_ref"]: row["id"] for row in listed.payload["accounts"]}
        # Saved accounts re-register at startup for the role stored with them.
        assert {
            row["config_ref"]: row["role_id"] for row in listed.payload["accounts"]
        } == {"aa": "mira", "bb": "other"}

        deleted = await plugin_bridge_request(
            service,
            "accounts.delete",
            {"account_id": accounts["aa"], "role_id": "mira"},
        )

        assert deleted.error is None, deleted.error
        after = await plugin_bridge_request(service, "accounts.list")
        assert [row["id"] for row in after.payload["accounts"]] == [accounts["bb"]]
        assert list(store.load()) == ["bb"]
        assert "secret-aa" not in store.path.read_text(encoding="utf-8")
        assert not napcat.account_dir("aa").exists()
        # Deletion is the plugin's alone: host configuration is untouched.
        assert path.read_text(encoding="utf-8") == config_before


def _verified(ref: str, uin: str, role_id: str) -> QQConnectionConfig:
    return QQConnectionConfig(
        ref,
        "ws://127.0.0.1:1",
        f"secret-{ref}",
        expected_uin=uin,
        auto_connect=False,
        verified=True,
        role_id=role_id,
    )


async def _restart_and_list(
    workspace: Path, staging: Path
) -> list[tuple[str, AccountResponseRules]]:
    """Loads the QQ plugin afresh on an existing workspace, as a restart does."""
    if not (staging / "qq").exists():
        stage_plugin_package(PLUGIN_DIR, staging / "qq")
    roles = RoleStore(workspace)
    kernel = PluginKernel(
        [staging],
        services=HostServices(
            event_bus=EventBus(),
            plugin_configs={},
            workspace=workspace,
            role_store=roles,
        ),
    )
    await kernel.load_all()
    try:
        return [
            (row.record.id, row.record.response_rules) for row in roles.accounts.list()
        ]
    finally:
        await kernel.terminate_all(force=True)


@pytest.mark.asyncio
async def test_rules_edited_on_the_host_survive_a_plugin_restart(
    plugin_runtime, tmp_path
) -> None:
    RoleStore(tmp_path).create_role(role_id="mira", name="Mira", system_prompt="m")
    store = QQAccountsStore(tmp_path)
    store.save({"aa": _verified("aa", "101", "mira")})
    rules = {
        "private_enabled": False,
        "group_enabled": True,
        "require_mention": False,
        "blocked_sender_ids": ["9"],
    }
    async with plugin_runtime(("qq",)) as (service, _path):
        saved = await plugin_bridge_request(
            service,
            "accounts.rules.set",
            {"account_id": "qq:101", "response_rules": rules},
        )
        assert saved.error is None, saved.error
    expected = AccountResponseRules(
        private_enabled=False, require_mention=False, blocked_sender_ids=("9",)
    )

    listed = await _restart_and_list(tmp_path, tmp_path / "staging")

    assert listed == [("qq:101", expected)]


@pytest.mark.asyncio
async def test_load_deletes_orphaned_accounts_and_temporary_napcat_files(
    tmp_path,
) -> None:
    RoleStore(tmp_path).create_role(role_id="mira", name="Mira", system_prompt="m")
    store = QQAccountsStore(tmp_path)
    store.save(
        {
            "aa": _verified("aa", "101", "gone"),
            "cc": _verified("cc", "303", "mira"),
            # Without an owner the data is kept for the user to fix.
            "dd": _verified("dd", "404", ""),
        }
    )
    napcat = NapCatAccountFiles(store.path.parent / "managed-napcat")
    # bb has no saved account: it is a temporary login left after a crash.
    for ref in ("aa", "bb"):
        napcat.account_dir(ref).mkdir(parents=True)

    listed = await _restart_and_list(tmp_path, tmp_path / "staging")

    assert [account_id for account_id, _rules in listed] == ["qq:303"]
    assert list(store.load()) == ["cc", "dd"]
    assert not napcat.account_dir("aa").exists()
    assert not napcat.account_dir("bb").exists()
