from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from typing import Any

import pytest
from shiori_plugin_testkit.packages import stage_plugin_package

from agent.plugin_host import HostServices, PluginKernel, load_manifest
from agent.plugin_host.kv import PluginKVStore
from bus.event_bus import EventBus
from core.roles.store import RoleStore
from plugins.qqbot.backend.accounts import QQBotAccountStore
from plugins.qqbot.backend.plugin import QQBotConfigModel

PLUGIN_DIR = Path(__file__).resolve().parents[1]


def _load_qqbot_channels(
    plugin_configs: dict[str, dict[str, Any]] | None = None,
) -> list[Any]:
    with tempfile.TemporaryDirectory() as tmp:
        plugin_dir = Path(tmp) / "qqbot"
        stage_plugin_package(PLUGIN_DIR, plugin_dir)
        kernel = PluginKernel(
            [Path(tmp)],
            services=HostServices(
                event_bus=EventBus(),
                plugin_configs=plugin_configs or {},
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


def test_qqbot_plugin_accepts_legacy_config_aliases() -> None:
    channels = _load_qqbot_channels(
        {
            "qqbot": {
                "appId": "app",
                "clientSecret": "secret",
                # Removed by the config migration; a leftover key is ignored.
                "allow_from": ["user-openid"],
            }
        }
    )

    assert len(channels) == 1
    assert channels[0].name == "qqbot"
    assert channels[0]._identity.account_id("app")


def test_qqbot_plugin_migrates_original_secret_reference() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        workspace = Path(tmp)
        plugin_dir = workspace / "qqbot"
        stage_plugin_package(PLUGIN_DIR, plugin_dir)
        kernel = PluginKernel(
            [workspace],
            services=HostServices(
                event_bus=EventBus(),
                workspace=workspace,
                role_store=RoleStore(workspace),
                plugin_configs={
                    "qqbot": {"app_id": "100", "client_secret": "expanded"}
                },
                raw_plugin_configs={
                    "qqbot": {"app_id": "100", "client_secret": "${QQBOT_SECRET}"}
                },
            ),
        )
        asyncio.run(kernel.load_all())
        assert kernel.loaded_count == 1
        store = QQBotAccountStore(
            PluginKVStore(workspace / "plugin-data" / "qqbot" / "kv.json")
        )
        assert store.get("100")["client_secret"] == "${QQBOT_SECRET}"


def test_qqbot_plugin_does_not_migrate_incomplete_legacy_credentials() -> None:
    [channel] = _load_qqbot_channels({"qqbot": {"app_id": "app"}})
    assert channel._identity.account_id("app") == ""


def test_qqbot_config_model_validates_directly() -> None:
    """QQBotConfigModel 的校验/别名规则单独测试，不依赖内核装配。"""
    config = QQBotConfigModel.model_validate(
        {"app_id": "${APP_ID}", "client_secret": "s"}
    )

    assert config.app_id == ""
    assert config.client_secret == "s"


@pytest.mark.asyncio
async def test_qqbot_setup_ignores_removed_group_settings() -> None:
    """A leftover legacy group field cannot block a C2C account migration."""
    with tempfile.TemporaryDirectory() as tmp:
        plugin_dir = Path(tmp) / "qqbot"
        stage_plugin_package(PLUGIN_DIR, plugin_dir)
        kernel = PluginKernel(
            [Path(tmp)],
            services=HostServices(
                event_bus=EventBus(),
                plugin_configs={"qqbot": {"groups": {"not": "a list"}}},
                workspace=Path(tmp),
                role_store=RoleStore(Path(tmp)),
            ),
        )
        await kernel.load_all()

        assert kernel.loaded_count == 1


def test_qqbot_channel_does_not_consume_bot_commands() -> None:
    # 不读 ctx.bot_commands，命令列表变化不应重建官方 QQBot 连接（#363）。
    from plugins.qqbot.backend.channel import QQBotChannel

    assert getattr(QQBotChannel, "uses_bot_commands", False) is False


def test_config_schema_labels_fields_for_the_settings_form() -> None:
    properties = QQBotConfigModel.model_json_schema()["properties"]
    auto_titles = {key: key.replace("_", " ").title() for key in properties}
    assert all(properties[key]["title"] != auto_titles[key] for key in properties)
    assert "groups" not in properties
    assert "allow_from" not in properties
