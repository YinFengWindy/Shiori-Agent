from __future__ import annotations

from pathlib import Path

import pytest
from shiori_sdk.testing.bridge import plugin_bridge_request
from shiori_sdk.testing.packages import stage_plugin_package

from agent.plugin_host import HostServices, PluginKernel
from bus.event_bus import EventBus
from core.accounts import AccountResponseRules
from core.roles.store import RoleStore
from core.net.http import SharedHttpResources
from plugins.qq.backend.accounts_store import QQAccountsStore, QQConnectionConfig
from plugins.qq.backend.napcat_account_files import NapCatAccountFiles

PLUGIN_DIR = Path(__file__).resolve().parents[4] / "plugins" / "qq"


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
    http_resources = SharedHttpResources()
    kernel = PluginKernel(
        [staging],
        services=HostServices(
            event_bus=EventBus(),
            plugin_configs={},
            workspace=workspace,
            role_store=roles,
            http=http_resources.external_default,
        ),
    )
    await kernel.load_all()
    try:
        return [
            (row.record.id, row.record.response_rules) for row in roles.accounts.list()
        ]
    finally:
        try:
            await kernel.terminate_all(force=True)
        finally:
            await http_resources.aclose()


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
        "blocked_sender_ids": ["9"],
    }
    async with plugin_runtime(("qq",)) as (service, _path):
        saved = await plugin_bridge_request(
            service,
            "accounts.rules.set",
            {"account_id": "qq:101", "response_rules": rules},
        )
        assert saved.error is None, saved.error
    expected = AccountResponseRules(private_enabled=False, blocked_sender_ids=("9",))

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
