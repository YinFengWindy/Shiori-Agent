from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from typing import Any

import pytest
from shiori_plugin_testkit.packages import stage_plugin_package

from agent.plugin_host import HostServices, PluginKernel, load_manifest
from bus.event_bus import EventBus
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
                event_bus=EventBus(), plugin_configs=plugin_configs or {}
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
    assert manifest.channels[0].contact_label


def test_qqbot_plugin_skips_channel_without_credentials() -> None:
    assert _load_qqbot_channels() == []


def test_qqbot_plugin_accepts_legacy_config_aliases() -> None:
    channels = _load_qqbot_channels(
        {
            "qqbot": {
                "appId": "app",
                "clientSecret": "secret",
                "allow_from": ["user-openid"],
            }
        }
    )

    assert len(channels) == 1
    assert channels[0].name == "qqbot"
    assert channels[0]._app_id == "app"
    assert channels[0]._client_secret == "secret"
    assert channels[0]._allow_from == {"user-openid"}


def test_qqbot_plugin_skips_channel_when_only_app_id_present() -> None:
    assert _load_qqbot_channels({"qqbot": {"app_id": "app"}}) == []


def test_qqbot_config_model_validates_directly() -> None:
    """QQBotConfigModel 的校验/别名规则单独测试，不依赖内核装配。"""
    config = QQBotConfigModel.model_validate(
        {"app_id": "${APP_ID}", "client_secret": "s"}
    )

    assert config.app_id == ""
    assert config.client_secret == "s"


@pytest.mark.asyncio
async def test_qqbot_setup_raises_on_invalid_config_and_kernel_rolls_back() -> None:
    """配置校验失败时插件加载失败并回滚，行为对齐旧 _load_plugin_config。"""
    with tempfile.TemporaryDirectory() as tmp:
        plugin_dir = Path(tmp) / "qqbot"
        stage_plugin_package(PLUGIN_DIR, plugin_dir)
        kernel = PluginKernel(
            [Path(tmp)],
            services=HostServices(
                event_bus=EventBus(),
                # allow_from 必须是 list[str]；传入非法类型触发 pydantic 校验错误
                plugin_configs={"qqbot": {"allow_from": {"not": "a list"}}},
            ),
        )
        await kernel.load_all()

        assert kernel.loaded_count == 0


def test_qqbot_channel_does_not_consume_bot_commands() -> None:
    # 不读 ctx.bot_commands，命令列表变化不应重建官方 QQBot 连接（#363）。
    from plugins.qqbot.backend.channel import QQBotChannel

    assert getattr(QQBotChannel, "uses_bot_commands", False) is False


def test_config_schema_labels_fields_for_the_settings_form() -> None:
    properties = QQBotConfigModel.model_json_schema()["properties"]
    auto_titles = {key: key.replace("_", " ").title() for key in properties}
    assert all(properties[key]["title"] != auto_titles[key] for key in properties)
    # allow_from renders as a list editor, not a raw JSON field.
    assert properties["allow_from"]["type"] == "array"
    assert properties["allow_from"]["items"] == {"type": "string"}
