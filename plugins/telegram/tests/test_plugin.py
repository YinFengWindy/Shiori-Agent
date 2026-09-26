from __future__ import annotations

import asyncio
import tempfile
import tomllib
from pathlib import Path
from typing import Any

from shiori_plugin_testkit.packages import stage_plugin_package

from agent.plugin_host import HostServices, PluginKernel, load_manifest
from core.roles.store import RoleStore
from desktop_bridge.plugin_config_text import merge_plugin_table
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
                event_bus=EventBus(),
                workspace=Path(tmp),
                role_store=RoleStore(Path(tmp)),
                plugin_configs=plugin_configs or {},
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
    assert set(manifest.capabilities) == {"config", "channels", "accounts", "kv", "rpc"}
    assert [item.name for item in manifest.channels] == ["telegram"]
    assert manifest.channels[0].label == "Telegram"
    # Labels the member IDs of a group binding's blacklist.
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
    assert channels[0].configuration_key is None


def test_two_bots_keep_distinct_channels_and_legacy_config() -> None:
    channels = _load_telegram_channels(
        {
            "telegram": {
                "token": "123:legacy",
                "bots": [{"ref": "second", "token": "456:new"}],
            }
        }
    )
    assert [(channel.name, channel._config_ref) for channel in channels] == [
        ("telegram", "legacy"),
        ("telegram_second", "second"),
    ]
    assert channels[0].user_map is not channels[1].user_map


def test_disabled_bot_does_not_remove_saved_configuration() -> None:
    config = TelegramConfigModel.model_validate(
        {
            "bots": [{"ref": "paused", "token": "456:new", "enabled": False}],
        }
    )
    assert config.configured_bots[0].ref == "paused"
    assert _load_telegram_channels({"telegram": config.model_dump()}) == []


def test_multi_bot_configuration_round_trips_through_plugin_table() -> None:
    values = TelegramConfigModel.model_validate(
        {
            "bots": [
                {"ref": "first", "token": "123:one"},
                {"ref": "second", "token": "456:two", "enabled": False},
            ],
        }
    ).model_dump()
    merged = merge_plugin_table(
        "[plugins.telegram]\ntoken = '123:legacy'\n", "telegram", values
    )
    assert tomllib.loads(merged)["plugins"]["telegram"] == values


def test_replacing_one_ref_with_another_bot_preserves_old_account(tmp_path) -> None:
    plugin_dir = tmp_path / "telegram"
    stage_plugin_package(PLUGIN_DIR, plugin_dir)
    role_store = RoleStore(tmp_path)
    original = role_store.accounts.register(
        plugin_id="telegram",
        platform="telegram",
        platform_account_id="123",
        config_ref="legacy",
        token="existing-runtime",
    )
    kernel = PluginKernel(
        [tmp_path],
        services=HostServices(
            event_bus=EventBus(),
            workspace=tmp_path,
            role_store=role_store,
            plugin_configs={"telegram": {"token": "456:other"}},
        ),
    )
    asyncio.run(kernel.load_all())
    assert kernel.loaded_count == 0
    assert (
        role_store.accounts.get(original.record.id).record.platform_account_id == "123"
    )


def test_unresolved_env_placeholder_counts_as_not_configured() -> None:
    assert TelegramConfigModel.model_validate({"token": "${TG_TOKEN}"}).token == ""
    assert TelegramConfigModel.model_validate({"token": " t "}).token == "t"


def test_config_schema_renders_token_as_secret_field() -> None:
    # 自动表单按字段名含 token 渲染密码框，title 作为中文标签。
    properties = TelegramConfigModel.model_json_schema()["properties"]
    assert list(properties) == ["token", "bots"]
    assert properties["token"]["title"] == "Bot Token"


def test_channels_are_generation_owned() -> None:
    from plugins.telegram.backend.channel import TelegramChannel

    assert TelegramChannel(token="123:abc").configuration_key is None


def test_channel_registers_bot_commands() -> None:
    from plugins.telegram.backend.channel import TelegramChannel

    assert TelegramChannel.uses_bot_commands is True
