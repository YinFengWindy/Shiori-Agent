from __future__ import annotations

import asyncio
import tempfile
import tomllib
from pathlib import Path
from typing import Any

import pytest
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
        role_store = RoleStore(Path(tmp))
        for role_id in ("mira", "other"):
            role_store.create_role(role_id=role_id, name=role_id, system_prompt="m")
        kernel = PluginKernel(
            [Path(tmp)],
            services=HostServices(
                event_bus=EventBus(),
                workspace=Path(tmp),
                role_store=role_store,
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


def test_only_bots_with_an_owner_role_contribute_channels() -> None:
    # The old single Token has no owner role, so it is not served.
    assert _load_telegram_channels({"telegram": {"token": "123:abc"}}) == []
    channels = _load_telegram_channels(
        {"telegram": {"bots": [{"ref": "main", "token": "123:abc", "role_id": "mira"}]}}
    )

    assert len(channels) == 1
    assert channels[0].name == "telegram_main"
    assert channels[0]._role_id == "mira"
    assert channels[0].configuration_key is None


def test_two_bots_keep_distinct_channels() -> None:
    channels = _load_telegram_channels(
        {
            "telegram": {
                "bots": [
                    {"ref": "legacy", "token": "123:legacy", "role_id": "mira"},
                    {"ref": "second", "token": "456:new", "role_id": "other"},
                ],
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
    role_store.create_role(role_id="mira", name="Mira", system_prompt="m")
    original = role_store.accounts.register(
        plugin_id="telegram",
        platform="telegram",
        platform_account_id="123",
        config_ref="legacy",
        token="existing-runtime",
        role_id="mira",
    )
    bot = {"ref": "legacy", "token": "456:other", "role_id": "mira"}
    kernel = PluginKernel(
        [tmp_path],
        services=HostServices(
            event_bus=EventBus(),
            workspace=tmp_path,
            role_store=role_store,
            plugin_configs={"telegram": {"bots": [bot]}},
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


def test_config_rejects_a_second_bot_for_a_role_or_a_repeated_bot() -> None:
    owned = {"ref": "one", "token": "123:a", "role_id": "mira"}
    with pytest.raises(ValueError, match="一个角色"):
        TelegramConfigModel.model_validate(
            {"bots": [owned, {"ref": "two", "token": "456:b", "role_id": "mira"}]}
        )
    with pytest.raises(ValueError, match="已添加"):
        TelegramConfigModel.model_validate(
            {"bots": [owned, {"ref": "two", "token": "123:a", "role_id": "other"}]}
        )
