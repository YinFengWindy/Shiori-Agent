from __future__ import annotations

import asyncio
import sys
import tempfile
from pathlib import Path
from typing import Any

import pytest
from shiori_plugin_testkit.bridge import plugin_bridge_request
from shiori_plugin_testkit.packages import stage_plugin_package

from agent.plugin_host import HostServices, PluginKernel, load_manifest
from agent.plugin_host.kv import PluginKVStore
from agent.plugin_host.plugin_data import plugin_data_dir
from bus.event_bus import EventBus
from core.roles.store import RoleStore
from plugins.qqbot.backend.accounts import QQBotAccountStore

PLUGIN_DIR = Path(__file__).resolve().parents[1]


def _load_qqbot_channels() -> list[Any]:
    with tempfile.TemporaryDirectory() as tmp:
        plugin_dir = Path(tmp) / "qqbot"
        stage_plugin_package(PLUGIN_DIR, plugin_dir)
        kernel = PluginKernel(
            [Path(tmp)],
            services=HostServices(
                event_bus=EventBus(),
                workspace=Path(tmp),
                role_store=RoleStore(Path(tmp)),
            ),
        )
        asyncio.run(kernel.load_all())
        assert kernel.loaded_count == 1
        return kernel.channels


def test_qqbot_manifest_declares_its_channel_for_binding_discovery() -> None:
    manifest = load_manifest(PLUGIN_DIR)
    assert manifest is not None
    assert [item.name for item in manifest.channels] == ["qqbot"]
    assert manifest.channels[0].label == "QQBot"
    # Private-only: there is no group blacklist whose member IDs need a label.
    assert manifest.channels[0].contact_label is None
    # Inbound C2C messages are addressed ``c2c:<openid>``; there are no group bindings.
    [private] = manifest.channels[0].chat_types
    assert (private.type, private.prefix) == ("private", "c2c:")


def test_qqbot_plugin_exposes_an_empty_account_channel() -> None:
    channels = _load_qqbot_channels()
    assert len(channels) == 1
    assert channels[0].name == "qqbot"
    assert channels[0]._channels == {}


def test_qqbot_channel_does_not_consume_bot_commands() -> None:
    # 不读 ctx.bot_commands，命令列表变化不应重建官方 QQBot 连接（#363）。
    from plugins.qqbot.backend.channel import QQBotChannel

    assert getattr(QQBotChannel, "uses_bot_commands", False) is False


def _offline_preflight(monkeypatch: pytest.MonkeyPatch) -> None:
    """Skips the network credential check in every loaded QQBot generation."""

    async def accept(_self: object, _app_id: str, _secret: str) -> None:
        return None

    for module in list(sys.modules.values()):
        mixin = getattr(module, "_AccountCommandsMixin", None)
        if mixin is not None:
            monkeypatch.setattr(mixin, "_preflight", accept)


def _seed(tmp_path: Path, *apps: tuple[str, str]) -> QQBotAccountStore:
    roles = RoleStore(tmp_path)
    for role_id in ("mira", "other"):
        roles.create_role(role_id=role_id, name=role_id, system_prompt="m")
    store = QQBotAccountStore(
        PluginKVStore(plugin_data_dir(tmp_path, "qqbot") / "kv.json")
    )
    for app_id, role_id in apps:
        store.save(
            {"app_id": app_id, "client_secret": f"secret-{app_id}", "role_id": role_id}
        )
    return store


@pytest.mark.asyncio
async def test_saved_rules_survive_a_plugin_restart_and_disabling_hides_accounts(
    plugin_runtime, tmp_path
) -> None:
    _seed(tmp_path, ("100", "mira"))
    rules = {
        "private_enabled": False,
        "group_enabled": True,
        "require_mention": True,
        "blocked_sender_ids": ["spam"],
        "group_rules": [],
    }
    async with plugin_runtime(("qqbot",)) as (service, _path):
        saved = await plugin_bridge_request(
            service,
            "accounts.rules.set",
            {"account_id": "qqbot:100", "response_rules": rules},
        )
        assert saved.error is None, saved.error
        for enabled in (False, True):
            toggled = await plugin_bridge_request(
                service,
                "plugins.setEnabled",
                {
                    "plugin_id": "qqbot",
                    "enabled": enabled,
                    "operation_id": str(enabled),
                },
            )
            assert toggled.error is None, toggled.error
            listed = await plugin_bridge_request(service, "accounts.list")
            if not enabled:
                # A disabled plugin's accounts are not listed at all.
                assert listed.payload["accounts"] == []
        # Restarted, the plugin registers the rules it saved itself.
        [restored] = listed.payload["accounts"]
        assert (restored["id"], restored["response_rules"]) == ("qqbot:100", rules)


@pytest.mark.asyncio
async def test_plugin_deletes_accounts_of_deleted_roles_without_host_config(
    plugin_runtime, tmp_path, monkeypatch
) -> None:
    store = _seed(tmp_path, ("100", "mira"), ("200", "other"), ("300", "gone"))
    async with plugin_runtime(("qqbot",)) as (service, path):
        config_text = path.read_text(encoding="utf-8")
        # The application of a role deleted while unloaded is purged at load.
        assert [row["app_id"] for row in store.list()] == ["100", "200"]
        listed = await plugin_bridge_request(service, "accounts.list")
        assert {row["id"]: row["role_id"] for row in listed.payload["accounts"]} == {
            "qqbot:100": "mira",
            "qqbot:200": "other",
        }

        deleted = await plugin_bridge_request(
            service, "accounts.delete", {"account_id": "qqbot:100", "role_id": "mira"}
        )
        assert deleted.error is None, deleted.error
        assert [row["app_id"] for row in store.list()] == ["200"]
        _offline_preflight(monkeypatch)
        added = await plugin_bridge_request(
            service,
            "plugin.qqbot.account.save",
            {"role_id": "mira", "app_id": "100", "client_secret": "secret-100"},
        )
        # The same application added again gets the same account ID back.
        assert added.error is None, added.error
        assert added.payload == {"account_id": "qqbot:100"}

        removed = await plugin_bridge_request(
            service, "roles.delete", {"role_id": "other"}
        )
        assert removed.error is None, removed.error
        assert removed.payload["deleted_accounts"] == ["qqbot:200"]
        assert [row["app_id"] for row in store.list()] == ["100"]
        # Accounts live in plugin data only; host settings never change.
        assert path.read_text(encoding="utf-8") == config_text
