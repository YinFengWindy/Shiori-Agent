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
from core.roles.store import RoleStore
from plugins.qq.backend.channel.formatting import GROUP_PREFIX
from plugins.qq.backend.plugin import QQConfigModel, _send_account

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


def test_manifest_declares_the_legacy_channel_name_for_bindings() -> None:
    # 渠道名是角色绑定（含 gqq: 群聊）与会话线程的键，必须保持内置时期的 qq。
    manifest = load_manifest(PLUGIN_DIR)
    assert manifest is not None
    assert manifest.id == "qq"
    assert manifest.display_name == "QQ（NapCat）"
    assert set(manifest.capabilities) == {
        "config",
        "channels",
        "accounts",
        "workspace",
        "rpc",
    }
    assert manifest.config_model == "QQConfigModel"
    assert [item.name for item in manifest.channels] == ["qq"]


def test_manifest_group_prefix_matches_the_transport_group_format() -> None:
    # 绑定面板按声明拼接前缀、宿主按声明校验；前缀必须与发送端识别群聊的格式一致。
    manifest = load_manifest(PLUGIN_DIR)
    assert manifest is not None
    types = {item.type: item.prefix for item in manifest.channels[0].chat_types}
    assert types == {"private": None, "group": GROUP_PREFIX}


def test_plugin_contributes_account_channel_without_legacy_bot_uin() -> None:
    assert len(_load_qq_channels()) == 1
    assert len(_load_qq_channels({"qq": {"bot_uin": "${QQ_UIN}"}})) == 1


def test_plugin_contributes_qq_channel_with_connection_settings() -> None:
    channels = _load_qq_channels(
        {
            "qq": {
                "bot_uin": 10001,
                "ws_uri": "ws://napcat.lan:3001",
                "ws_token": "secret",
                "websocket_open_timeout_seconds": 9.5,
            }
        }
    )

    assert len(channels) == 1
    assert channels[0].name == "qq"
    assert channels[0].configuration_key[0] == "qq-accounts"
    assert channels[0]._configs["legacy"].expected_uin == "10001"
    assert channels[0]._configs["legacy"].ws_uri == "ws://napcat.lan:3001"
    assert channels[0]._configs["legacy"].ws_token == "secret"


def test_config_schema_labels_and_secret_field() -> None:
    # 自动表单：title 作中文标签，字段名含 token 的渲染为密码框。
    properties = QQConfigModel.model_json_schema()["properties"]
    assert list(properties) == [
        "bot_uin",
        "ws_uri",
        "ws_token",
        "websocket_open_timeout_seconds",
    ]
    assert properties["bot_uin"]["title"] == "Bot QQ 号"
    assert properties["ws_token"]["title"] == "NapCat WebSocket 令牌"


def test_timeout_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        QQConfigModel.model_validate({"websocket_open_timeout_seconds": 0})


@pytest.mark.asyncio
async def test_shared_account_send_adapts_target_and_rejects_topic() -> None:
    from unittest.mock import AsyncMock

    runtime = type(
        "Runtime", (), {"send_target": AsyncMock(return_value={"message_id": "9"})}
    )()
    payload = {
        "account_id": "account-1",
        "target_kind": "group",
        "target_id": "42",
        "message": "hello",
    }
    assert await _send_account(runtime, payload) == {"message_id": "9"}
    runtime.send_target.assert_awaited_once_with("account-1", "group", "42", "hello")
    with pytest.raises(ValueError, match="话题"):
        await _send_account(runtime, {**payload, "message_thread_id": 7})


def test_channel_does_not_consume_bot_commands() -> None:
    # NapCat 不读 ctx.bot_commands，命令列表变化不应重建连接（#363）。
    from plugins.qq.backend.channel.lifecycle import QQChannel

    assert getattr(QQChannel, "uses_bot_commands", False) is False
