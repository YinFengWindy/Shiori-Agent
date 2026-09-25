from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from typing import Any

from shiori_plugin_testkit.packages import stage_plugin_package

from agent.plugin_host import HostServices, PluginKernel, load_manifest
from bus.event_bus import EventBus
from plugins.telegram.backend.plugin import TelegramConfigModel

PLUGIN_DIR = Path(__file__).resolve().parents[1]


def _load_telegram_channels(
    plugin_configs: dict[str, dict[str, Any]] | None = None,
) -> list[Any]:
    with tempfile.TemporaryDirectory() as tmp:
        plugin_dir = Path(tmp) / "telegram"
        stage_plugin_package(PLUGIN_DIR, plugin_dir)
        kernel = PluginKernel(
            [Path(tmp)],
            services=HostServices(
                event_bus=EventBus(), plugin_configs=plugin_configs or {}
            ),
        )
        asyncio.run(kernel.load_all())
        assert kernel.loaded_count == 1
        return kernel.channels


def test_manifest_declares_the_legacy_channel_name_for_bindings() -> None:
    # 渠道名就是角色绑定与会话线程的键，必须保持内置时期的 telegram。
    manifest = load_manifest(PLUGIN_DIR)
    assert manifest is not None
    assert manifest.id == "telegram"
    assert set(manifest.capabilities) == {"config", "channels"}
    assert [item.name for item in manifest.channels] == ["telegram"]
    assert manifest.channels[0].label == "Telegram"
    assert manifest.channels[0].contact_label
    # Telegram group IDs are negative numbers without a prefix.
    types = {item.type: item.prefix for item in manifest.channels[0].chat_types}
    assert types == {"private": None, "group": None}


def test_plugin_skips_channel_without_token() -> None:
    assert _load_telegram_channels() == []
    assert _load_telegram_channels({"telegram": {"token": "  "}}) == []


def test_plugin_contributes_telegram_channel_with_token() -> None:
    channels = _load_telegram_channels({"telegram": {"token": "123:abc"}})

    assert len(channels) == 1
    assert channels[0].name == "telegram"
    assert channels[0].configuration_key == ("telegram", "123:abc")


def test_unresolved_env_placeholder_counts_as_not_configured() -> None:
    assert TelegramConfigModel.model_validate({"token": "${TG_TOKEN}"}).token == ""
    assert TelegramConfigModel.model_validate({"token": " t "}).token == "t"


def test_config_schema_renders_token_as_secret_field() -> None:
    # 自动表单按字段名含 token 渲染密码框，title 作为中文标签。
    properties = TelegramConfigModel.model_json_schema()["properties"]
    assert list(properties) == ["token"]
    assert properties["token"]["title"] == "Bot Token"


def test_configuration_key_tracks_only_the_token() -> None:
    # 宿主把 bot 命令拼进复用键；插件只负责凭据部分。
    from plugins.telegram.backend.channel import TelegramChannel

    same = TelegramChannel(token="123:abc").configuration_key
    assert TelegramChannel(token="123:abc").configuration_key == same
    assert TelegramChannel(token="456:def").configuration_key != same


def test_channel_opts_into_bot_command_reuse_checks() -> None:
    # 命令菜单在 start 时注册，命令变化必须重建连接（#363）。
    from plugins.telegram.backend.channel import TelegramChannel

    assert TelegramChannel.uses_bot_commands is True
