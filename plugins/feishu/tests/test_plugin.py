from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
import httpx
from shiori_plugin_testkit.packages import stage_plugin_package
from shiori_plugin_testkit.bridge import plugin_bridge_request

from agent.plugin_host import HostServices, PluginKernel, load_manifest
from bus.event_bus import EventBus
from core.accounts import AccountSnapshot
from core.accounts.target_contract import UncertainDeliveryError
from core.roles.store import RoleStore
from plugins.feishu.backend.plugin import setup

PLUGIN_DIR = Path(__file__).resolve().parents[1]


@pytest.mark.asyncio
async def test_shared_account_rpc_uses_selected_private_application() -> None:
    handlers: dict[str, Any] = {}
    channels: list[Any] = []
    ctx = SimpleNamespace(
        config=SimpleNamespace(
            as_dict=lambda: {
                "app_id": "cli_a",
                "app_secret": "secret",
                "domain": "feishu",
            }
        ),
        kv=SimpleNamespace(
            get=lambda key, default: (
                {"oc_chat": "ou_user"} if key.startswith("targets:") else default
            )
        ),
        rpc=SimpleNamespace(
            register=lambda name, handler, **kwargs: handlers.__setitem__(name, handler)
        ),
        accounts=SimpleNamespace(
            register=lambda **kwargs: SimpleNamespace(
                record=SimpleNamespace(id="account-a")
            ),
            report=lambda *args, **kwargs: None,
        ),
        channels=SimpleNamespace(add=channels.append),
        manifest=SimpleNamespace(channel_chat_types=lambda name: ()),
    )
    await setup(ctx)
    assert (
        await handlers["account.targets"]({"account_id": "account-a", "kind": "known"})
    )["coverage"] == "observed_private_chats"
    channels[0].send = AsyncMock(return_value="om_9")
    assert await handlers["account.send"](
        {
            "account_id": "account-a",
            "target_kind": "private",
            "target_id": "oc_chat",
            "message": "hello",
        }
    ) == {"message_id": "om_9"}
    channels[0].send.assert_awaited_once_with("oc_chat", "hello")
    channels[0].send.return_value = None
    with pytest.raises(UncertainDeliveryError):
        await handlers["account.send"](
            {
                "account_id": "account-a",
                "target_kind": "private",
                "target_id": "oc_chat",
                "message": "hello",
            }
        )
    channels[0].send.side_effect = httpx.ReadTimeout("reply lost")
    with pytest.raises(UncertainDeliveryError):
        await handlers["account.send"](
            {
                "account_id": "account-a",
                "target_kind": "private",
                "target_id": "oc_chat",
                "message": "hello",
            }
        )
    with pytest.raises(ValueError, match="私聊"):
        await handlers["account.send"](
            {"account_id": "account-a", "target_kind": "group"}
        )


def _load_feishu_state(
    plugin_configs: dict[str, dict[str, Any]] | None = None,
) -> tuple[int, list[Any], list[AccountSnapshot]]:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        stage_plugin_package(PLUGIN_DIR, root / "feishu")
        roles = RoleStore(root)
        kernel = PluginKernel(
            [root],
            services=HostServices(
                event_bus=EventBus(),
                plugin_configs=plugin_configs or {},
                workspace=root,
                role_store=roles,
            ),
        )
        asyncio.run(kernel.load_all())
        return kernel.loaded_count, kernel.channels, roles.accounts.list()


def _load_feishu_channels(
    plugin_configs: dict[str, dict[str, Any]] | None = None,
) -> tuple[int, list[Any]]:
    count, channels, _ = _load_feishu_state(plugin_configs)
    return count, channels


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
    assert channel.configuration_key[:5] == (
        "feishu",
        "feishu",
        "cli_a",
        "s",
        "https://open.larksuite.com",
    )


def test_two_regional_apps_register_distinct_accounts_and_channels() -> None:
    loaded, channels, accounts = _load_feishu_state(
        {
            "feishu": {
                "accounts": [
                    {"app_id": "cli_a", "app_secret": "first", "domain": "feishu"},
                    {"app_id": "cli_b", "app_secret": "second", "domain": "lark"},
                ]
            }
        }
    )
    assert loaded == 1
    assert [channel.name for channel in channels] == [
        "feishu:feishu:cli_a",
        "feishu:lark:cli_b",
    ]
    assert {row.record.platform_account_id for row in accounts} == {
        "feishu:cli_a",
        "lark:cli_b",
    }
    assert all(row.connection == "connecting" for row in accounts)
    assert all("secret" not in str(row) for row in accounts)


def test_reordering_accounts_keeps_the_legacy_channel_alias_stable() -> None:
    old = {"app_id": "cli_old", "app_secret": "old", "domain": "lark"}
    new = {"app_id": "cli_new", "app_secret": "new", "domain": "feishu"}
    for order in ([old, new], [new, old]):
        loaded, channels = _load_feishu_channels(
            {
                "feishu": {
                    "legacy_channel_ref": "lark:cli_old",
                    "accounts": order,
                }
            }
        )
        assert loaded == 1
        assert {channel.configuration_key[2]: channel.name for channel in channels} == {
            "cli_old": "feishu",
            "cli_new": "feishu:feishu:cli_new",
        }


def test_invalid_config_fails_the_plugin_and_rolls_back() -> None:
    loaded, channels = _load_feishu_channels(
        {"feishu": {"app_id": "a", "app_secret": "s", "domain": "https://evil"}}
    )

    assert (loaded, channels) == (0, [])


def test_one_unresolved_secret_does_not_disable_another_account() -> None:
    loaded, channels, accounts = _load_feishu_state(
        {
            "feishu": {
                "accounts": [
                    {"app_id": "cli_ready", "app_secret": "ready", "domain": "feishu"},
                    {
                        "app_id": "cli_missing",
                        "app_secret": "${MISSING_SECRET}",
                        "domain": "lark",
                    },
                ]
            }
        }
    )
    assert loaded == 1
    assert [channel.name for channel in channels] == ["feishu:feishu:cli_ready"]
    assert {row.record.platform_account_id: row.connection for row in accounts} == {
        "feishu:cli_ready": "connecting",
        "lark:cli_missing": "login_required",
    }


def test_disconnected_app_keeps_identity_while_other_channel_runs() -> None:
    loaded, channels, accounts = _load_feishu_state(
        {
            "feishu": {
                "accounts": [
                    {
                        "app_id": "cli_off",
                        "app_secret": "off",
                        "domain": "feishu",
                        "connection_enabled": False,
                    },
                    {"app_id": "cli_on", "app_secret": "on", "domain": "lark"},
                ]
            }
        }
    )
    assert loaded == 1
    assert [channel.name for channel in channels] == ["feishu:lark:cli_on"]
    assert {row.record.platform_account_id: row.connection for row in accounts} == {
        "feishu:cli_off": "offline",
        "lark:cli_on": "connecting",
    }


@pytest.mark.asyncio
async def test_config_transaction_migrates_legacy_app_without_changing_account_identity(
    plugin_runtime,
) -> None:
    initial = (
        '\n[plugins.feishu]\napp_id = "cli_old"\napp_secret = "old"\ndomain = "lark"\n'
    )
    async with plugin_runtime(("feishu",), initial) as (service, path):
        before = await plugin_bridge_request(service, "accounts.list")
        assert before.error is None, before.error
        [old] = before.payload["accounts"]

        saved = await plugin_bridge_request(
            service,
            "plugin.config.set",
            {
                "plugin_id": "feishu",
                "operation_id": "migrate-feishu",
                "values": {
                    "app_id": "",
                    "app_secret": "",
                    "domain": "feishu",
                    "legacy_channel_ref": "lark:cli_old",
                    "accounts": [
                        {"app_id": "cli_old", "app_secret": "old", "domain": "lark"},
                        {"app_id": "cli_new", "app_secret": "new", "domain": "feishu"},
                    ],
                },
            },
        )
        assert saved.error is None, saved.error
        after = await plugin_bridge_request(service, "accounts.list")
        assert after.error is None, after.error
        rows = after.payload["accounts"]
        assert {row["platform_account_id"] for row in rows} == {
            "lark:cli_old",
            "feishu:cli_new",
        }
        assert (
            next(row for row in rows if row["platform_account_id"] == "lark:cli_old")[
                "id"
            ]
            == old["id"]
        )
        assert 'app_secret = "old"' in path.read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_disconnect_and_reconnect_keep_the_saved_account(plugin_runtime) -> None:
    initial = '\n[plugins.feishu]\n[[plugins.feishu.accounts]]\napp_id = "cli_a"\napp_secret = "secret"\ndomain = "feishu"\n'
    async with plugin_runtime(("feishu",), initial) as (service, _path):
        before = await plugin_bridge_request(service, "accounts.list")
        [original] = before.payload["accounts"]
        for operation, enabled, expected in (
            ("disconnect-feishu", False, "offline"),
            ("reconnect-feishu", True, "connecting"),
        ):
            saved = await plugin_bridge_request(
                service,
                "plugin.config.set",
                {
                    "plugin_id": "feishu",
                    "operation_id": operation,
                    "values": {
                        "app_id": "",
                        "app_secret": "",
                        "domain": "feishu",
                        "accounts": [
                            {
                                "app_id": "cli_a",
                                "app_secret": "secret",
                                "domain": "feishu",
                                "connection_enabled": enabled,
                            }
                        ],
                    },
                },
            )
            assert saved.error is None, saved.error
            listed = await plugin_bridge_request(service, "accounts.list")
            [account] = listed.payload["accounts"]
            assert account["id"] == original["id"]
            assert account["connection"] == expected
