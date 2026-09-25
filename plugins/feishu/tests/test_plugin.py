from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError
from shiori_plugin_testkit.packages import stage_plugin_package

from agent.plugin_host import HostServices, PluginKernel, load_manifest
from bus.event_bus import EventBus
from plugins.feishu.backend.plugin import FeishuConfigModel

PLUGIN_DIR = Path(__file__).resolve().parents[1]


def _load_feishu_channels(
    plugin_configs: dict[str, dict[str, Any]] | None = None,
) -> tuple[int, list[Any]]:
    with tempfile.TemporaryDirectory() as tmp:
        stage_plugin_package(PLUGIN_DIR, Path(tmp) / "feishu")
        kernel = PluginKernel(
            [Path(tmp)],
            services=HostServices(
                event_bus=EventBus(), plugin_configs=plugin_configs or {}
            ),
        )
        asyncio.run(kernel.load_all())
        return kernel.loaded_count, kernel.channels


def test_manifest_declares_the_feishu_channel_for_binding_discovery() -> None:
    manifest = load_manifest(PLUGIN_DIR)

    assert manifest is not None
    assert manifest.display_name == "飞书"
    [channel] = manifest.channels
    assert (channel.name, channel.label) == ("feishu", "飞书")
    # Private-only: there is no group blacklist whose member IDs need a label.
    assert channel.contact_label is None
    [private] = channel.chat_types
    assert (private.type, private.prefix) == ("private", None)
    assert (private.chat_id_hint or "").startswith("oc_")


def test_plugin_contributes_nothing_without_credentials() -> None:
    assert _load_feishu_channels() == (1, [])
    assert _load_feishu_channels({"feishu": {"app_id": "cli_a"}}) == (1, [])
    # An unresolved ${ENV} placeholder counts as missing.
    assert _load_feishu_channels(
        {"feishu": {"app_id": "cli_a", "app_secret": "${FEISHU_SECRET}"}}
    ) == (1, [])


def test_plugin_contributes_the_channel_with_credentials() -> None:
    loaded, channels = _load_feishu_channels(
        {"feishu": {"app_id": "cli_a", "app_secret": "s", "domain": "lark"}}
    )

    assert loaded == 1
    [channel] = channels
    assert channel.name == "feishu"
    assert channel.configuration_key[:4] == (
        "feishu",
        "cli_a",
        "s",
        "https://open.larksuite.com",
    )


def test_invalid_config_fails_the_plugin_and_rolls_back() -> None:
    loaded, channels = _load_feishu_channels(
        {"feishu": {"app_id": "a", "app_secret": "s", "domain": "https://evil"}}
    )

    assert (loaded, channels) == (0, [])


def test_config_model_normalizes_legacy_domains_and_rejects_others() -> None:
    legacy = FeishuConfigModel.model_validate(
        {"app_id": " a ", "app_secret": "s", "domain": "https://open.larksuite.com/"}
    )

    assert (legacy.app_id, legacy.domain) == ("a", "lark")
    assert legacy.base_url == "https://open.larksuite.com"
    assert FeishuConfigModel().base_url == "https://open.feishu.cn"
    with pytest.raises(ValidationError):
        FeishuConfigModel.model_validate({"domain": "open.example.com"})


def test_config_schema_renders_as_a_labelled_form() -> None:
    properties = FeishuConfigModel.model_json_schema()["properties"]

    assert list(properties) == ["app_id", "app_secret", "domain"]
    assert properties["domain"]["enum"] == ["feishu", "lark"]
    assert all(item.get("title") for item in properties.values())
