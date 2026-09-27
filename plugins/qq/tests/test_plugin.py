from __future__ import annotations

import asyncio
import tomllib
import tempfile
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError
from shiori_plugin_testkit.bridge import plugin_bridge_request
from shiori_plugin_testkit.packages import stage_plugin_package

from agent.plugin_host import HostServices, PluginKernel, load_manifest
from bus.event_bus import EventBus
from core.roles.store import RoleStore
from plugins.qq.backend.channel.formatting import GROUP_PREFIX
from plugins.qq.backend.accounts_store import QQAccountsStore, QQConnectionConfig
from plugins.qq.backend.napcat_account_files import NapCatAccountFiles
from plugins.qq.backend.plugin import QQConfigModel, _send_account, setup

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
        "config",
        "channels",
        "accounts",
        "workspace",
        "rpc",
    }
    assert manifest.config_model == "QQConfigModel"
    assert [item.name for item in manifest.channels] == ["qq"]


def test_manifest_group_prefix_matches_the_transport_group_format() -> None:
    # Account intake and outbound target validation share the group prefix.
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


@pytest.mark.asyncio
async def test_delete_hook_retires_the_legacy_host_connection_fields(
    tmp_path,
) -> None:
    from types import SimpleNamespace

    hooks: list[Any] = []
    raw = {
        "bot_uin": "101",
        "ws_uri": "ws://localhost:3001",
        "ws_token": "${QQ_TOKEN}",
        "websocket_open_timeout_seconds": 5.0,
        "note": "keep",
    }
    ctx = SimpleNamespace(
        config=SimpleNamespace(as_dict=lambda: dict(raw), raw_as_dict=lambda: raw),
        workspace=tmp_path,
        accounts=SimpleNamespace(on_delete=hooks.append),
        channels=SimpleNamespace(add=lambda channel: None),
        rpc=SimpleNamespace(register=lambda *args, **kwargs: None),
    )
    await setup(ctx)
    [delete] = hooks

    other = delete("abc123")
    legacy = delete("legacy")

    assert other.plugin_config is None
    assert legacy.plugin_config == {"note": "keep"}
    # Planning left the migrated legacy connection in place.
    assert list(QQAccountsStore(tmp_path).load()) == ["legacy"]
    await legacy.disconnect()
    await legacy.purge()
    assert QQAccountsStore(tmp_path).load() == {}
    # A retry after a failed config write plans the same config removal.
    retried = delete("legacy")
    assert retried.plugin_config == {"note": "keep"}
    await retried.disconnect()
    await retried.purge()


@pytest.mark.asyncio
async def test_deleting_an_account_removes_credentials_napcat_data_and_record(
    plugin_runtime, tmp_path
) -> None:
    RoleStore(tmp_path).create_role(role_id="mira", name="Mira", system_prompt="m")
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
            )
            for ref, uin in (("aa", "101"), ("bb", "202"))
        }
    )
    napcat = NapCatAccountFiles(store.path.parent / "managed-napcat")
    login = napcat.account_dir("aa") / "profile/AppData/Roaming/Tencent/QQNT"
    login.mkdir(parents=True)
    (login / "session.db").write_text("login", encoding="utf-8")
    async with plugin_runtime(("qq",)) as (service, _path):
        listed = await plugin_bridge_request(service, "accounts.list")
        accounts = {row["config_ref"]: row["id"] for row in listed.payload["accounts"]}
        assigned = await plugin_bridge_request(
            service,
            "accounts.assign",
            {"account_id": accounts["aa"], "role_id": "mira"},
        )
        assert assigned.error is None, assigned.error

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
    assert [row.record.id for row in RoleStore(tmp_path).accounts.list()] == [
        accounts["bb"]
    ]


@pytest.mark.asyncio
async def test_deleting_the_legacy_account_survives_the_config_generation_swap(
    plugin_runtime, tmp_path
) -> None:
    RoleStore(tmp_path).create_role(role_id="mira", name="Mira", system_prompt="m")
    store = QQAccountsStore(tmp_path)
    # A different stored token keeps the host fields from being retired early.
    store.save(
        {
            "legacy": QQConnectionConfig(
                "legacy",
                "ws://127.0.0.1:1",
                "stored-token",
                expected_uin="101",
                auto_connect=False,
                verified=True,
            )
        }
    )
    napcat = NapCatAccountFiles(store.path.parent / "managed-napcat")
    login = napcat.account_dir("legacy") / "profile/AppData/Local/QQ"
    login.mkdir(parents=True)
    (login / "session.db").write_text("login", encoding="utf-8")
    config = (
        '\n[plugins.qq]\nbot_uin = "101"\nws_uri = "ws://127.0.0.1:1"\n'
        'ws_token = "legacy-token"\n'
    )
    async with plugin_runtime(("qq",), config) as (service, path):
        listed = await plugin_bridge_request(service, "accounts.list")
        [account] = listed.payload["accounts"]
        assert account["config_ref"] == "legacy"
        assigned = await plugin_bridge_request(
            service, "accounts.assign", {"account_id": account["id"], "role_id": "mira"}
        )
        assert assigned.error is None, assigned.error

        deleted = await plugin_bridge_request(
            service,
            "accounts.delete",
            {"account_id": account["id"], "role_id": "mira"},
        )

        assert deleted.error is None, deleted.error
        table = tomllib.loads(path.read_text(encoding="utf-8"))["plugins"].get("qq", {})
        assert not any(table.get(key) for key in ("bot_uin", "ws_uri", "ws_token"))
        assert "legacy-token" not in path.read_text(encoding="utf-8")
        assert store.load() == {}
        assert not napcat.account_dir("legacy").exists()
        # The generation published by the config write started without it.
        settings = await plugin_bridge_request(
            service, "plugin.qq.accounts.settings", {}
        )
        assert settings.error is None, settings.error
        assert settings.payload["accounts"] == []
        after = await plugin_bridge_request(service, "accounts.list")
        assert after.payload["accounts"] == []
    assert RoleStore(tmp_path).accounts.list() == []
    restarted = QQAccountsStore(tmp_path)
    restarted.migrate_legacy(
        bot_uin=str(table.get("bot_uin") or ""),
        ws_uri=str(table.get("ws_uri") or ""),
        ws_token=str(table.get("ws_token") or ""),
        timeout_seconds=float(table.get("websocket_open_timeout_seconds", 5.0)),
    )
    assert restarted.load() == {}
