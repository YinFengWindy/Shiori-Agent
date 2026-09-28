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
from agent.plugin_host.kv import PluginKVStore
from agent.plugin_host.plugin_data import plugin_data_dir
from plugins.feishu.backend.plugin import setup

PLUGIN_DIR = Path(__file__).resolve().parents[1]


@pytest.mark.asyncio
async def test_shared_account_rpc_uses_selected_private_application() -> None:
    handlers: dict[str, Any] = {}
    channels: list[Any] = []
    ctx = SimpleNamespace(
        config=SimpleNamespace(
            as_dict=lambda: {
                "accounts": [
                    {
                        "app_id": "cli_a",
                        "app_secret": "secret",
                        "domain": "feishu",
                        "role_id": "mira",
                    }
                ]
            },
            raw_as_dict=dict,
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
            register_configured=lambda **kwargs: SimpleNamespace(
                record=SimpleNamespace(id="account-a")
            ),
            read_config_accounts=lambda reader: None,
            report=lambda *args, **kwargs: None,
            on_delete=lambda handler: None,
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
        for role_id in ("mira", "other"):
            roles.create_role(role_id=role_id, name=role_id, system_prompt="m")
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
    # The old single app has no owner role, so it is not served.
    assert _load_feishu_state(
        {"feishu": {"app_id": "cli_a", "app_secret": "s", "domain": "lark"}}
    )[1:] == ([], [])
    loaded, channels, accounts = _load_feishu_state(
        {
            "feishu": {
                "legacy_channel_ref": "lark:cli_a",
                "accounts": [
                    {
                        "app_id": "cli_a",
                        "app_secret": "s",
                        "domain": "lark",
                        "role_id": "mira",
                    }
                ],
            }
        }
    )
    assert [row.record.role_id for row in accounts] == ["mira"]

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
                    {
                        "app_id": "cli_a",
                        "app_secret": "first",
                        "domain": "feishu",
                        "role_id": "mira",
                    },
                    {
                        "app_id": "cli_b",
                        "app_secret": "second",
                        "domain": "lark",
                        "role_id": "other",
                    },
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
    old = {
        "app_id": "cli_old",
        "app_secret": "old",
        "domain": "lark",
        "role_id": "mira",
    }
    new = {"app_id": "cli_new", "app_secret": "new", "domain": "feishu"}
    new["role_id"] = "other"
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
                    {
                        "app_id": "cli_ready",
                        "app_secret": "ready",
                        "domain": "feishu",
                        "role_id": "mira",
                    },
                    {
                        "app_id": "cli_missing",
                        "app_secret": "${MISSING_SECRET}",
                        "domain": "lark",
                        "role_id": "other",
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
                        "role_id": "mira",
                    },
                    {
                        "app_id": "cli_on",
                        "app_secret": "on",
                        "domain": "lark",
                        "role_id": "other",
                    },
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
async def test_config_save_cannot_give_one_role_a_second_application(
    plugin_runtime, tmp_path
) -> None:
    roles = RoleStore(tmp_path)
    for role_id in ("mira", "other"):
        roles.create_role(role_id=role_id, name=role_id, system_prompt="m")
    old = {
        "app_id": "cli_old",
        "app_secret": "old",
        "domain": "lark",
        "role_id": "mira",
    }
    initial = (
        '\n[plugins.feishu]\n[[plugins.feishu.accounts]]\napp_id = "cli_old"\n'
        'app_secret = "old"\ndomain = "lark"\nrole_id = "mira"\n'
    )
    async with plugin_runtime(("feishu",), initial) as (service, path):
        [before] = (await plugin_bridge_request(service, "accounts.list")).payload[
            "accounts"
        ]
        assert before["role_id"] == "mira"

        async def save(owner: str, operation: str):
            new = {"app_id": "cli_new", "app_secret": "new", "domain": "feishu"}
            return await plugin_bridge_request(
                service,
                "plugin.config.set",
                {
                    "plugin_id": "feishu",
                    "operation_id": operation,
                    "values": {"accounts": [old, {**new, "role_id": owner}]},
                },
            )

        rejected = await save("mira", "second-for-mira")
        assert rejected.error is not None
        assert rejected.error.code == "plugin_account_refused"
        assert "cli_new" not in path.read_text(encoding="utf-8")
        # An app's owner is fixed: another role cannot take it over by a write.
        moved = await plugin_bridge_request(
            service,
            "plugin.config.set",
            {
                "plugin_id": "feishu",
                "operation_id": "move-to-other",
                "values": {"accounts": [{**old, "role_id": "other"}]},
            },
        )
        assert moved.error is not None and "不能更改" in moved.error.message
        accepted = await save("other", "first-for-other")
        assert accepted.error is None, accepted.error
        rows = (await plugin_bridge_request(service, "accounts.list")).payload[
            "accounts"
        ]
        assert {row["platform_account_id"]: row["role_id"] for row in rows} == {
            "lark:cli_old": "mira",
            "feishu:cli_new": "other",
        }
        assert before["id"] in {row["id"] for row in rows}


@pytest.mark.asyncio
async def test_one_unusable_app_is_reported_while_the_others_still_run(
    plugin_runtime, tmp_path
) -> None:
    RoleStore(tmp_path).create_role(role_id="mira", name="Mira", system_prompt="m")
    initial = (
        '\n[plugins.feishu]\napp_id = "cli_old"\napp_secret = "old"\n'
        '[[plugins.feishu.accounts]]\napp_id = "cli_ok"\napp_secret = "s"\n'
        'role_id = "mira"\n'
        '[[plugins.feishu.accounts]]\napp_id = "cli_gone"\napp_secret = "s"\n'
        'role_id = "deleted-role"\n'
    )
    async with plugin_runtime(("feishu",), initial) as (service, _path):
        listed = await plugin_bridge_request(service, "accounts.list")
        assert [row["platform_account_id"] for row in listed.payload["accounts"]] == [
            "feishu:cli_ok"
        ]
        plugins = await plugin_bridge_request(service, "plugins.list")
        [feishu] = [row for row in plugins.payload["plugins"] if row["id"] == "feishu"]
        assert feishu["state"] == "ACTIVE"
        errors = feishu["account_errors"]
        assert len(errors) == 2
        assert "feishu:cli_old" in errors[0] and "没有所属角色" in errors[0]
        assert "feishu:cli_gone" in errors[1] and "角色不存在" in errors[1]


@pytest.mark.asyncio
async def test_disconnect_and_reconnect_keep_the_saved_account(
    plugin_runtime, tmp_path
) -> None:
    RoleStore(tmp_path).create_role(role_id="mira", name="Mira", system_prompt="m")
    initial = (
        '\n[plugins.feishu]\n[[plugins.feishu.accounts]]\napp_id = "cli_a"\n'
        'app_secret = "secret"\ndomain = "feishu"\nrole_id = "mira"\n'
    )
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
                                "role_id": "mira",
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


@pytest.mark.asyncio
async def test_deleting_an_application_purges_config_caches_and_host_record(
    plugin_runtime, tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("FEISHU_GONE_ID", "cli_gone")
    monkeypatch.setenv("FEISHU_KEEP_ID", "cli_keep")
    roles = RoleStore(tmp_path)
    for role_id in ("mira", "other", "keeper"):
        roles.create_role(role_id=role_id, name=role_id, system_prompt="m")
    initial = (
        '\n[plugins.feishu]\nlegacy_channel_ref = "lark:cli_old"\n'
        '[[plugins.feishu.accounts]]\napp_id = "cli_old"\napp_secret = "old"\n'
        'domain = "lark"\nrole_id = "mira"\n'
        '[[plugins.feishu.accounts]]\napp_id = "${FEISHU_GONE_ID}"\n'
        'app_secret = "gone-secret"\ndomain = "feishu"\nrole_id = "other"\n'
        '[[plugins.feishu.accounts]]\napp_id = "${FEISHU_KEEP_ID}"\n'
        'app_secret = "${FEISHU_KEEP_SECRET}"\ndomain = "feishu"\n'
        'role_id = "keeper"\n'
    )
    async with plugin_runtime(("feishu",), initial) as (service, path):
        listed = await plugin_bridge_request(service, "accounts.list")
        accounts = {
            row["platform_account_id"]: row["id"] for row in listed.payload["accounts"]
        }
        kv = PluginKVStore(plugin_data_dir(tmp_path, "feishu") / "kv.json")
        for key in ("profile", "targets"):
            kv.set(f"{key}:lark:cli_old", {"stale": True})
            kv.set(f"{key}:feishu:cli_keep", {"kept": True})
        for ref, owner in (("lark:cli_old", "mira"), ("feishu:cli_gone", "other")):
            deleted = await plugin_bridge_request(
                service,
                "accounts.delete",
                {"account_id": accounts[ref], "role_id": owner},
            )
            assert deleted.error is None, deleted.error

        after = await plugin_bridge_request(service, "accounts.list")
        assert [row["id"] for row in after.payload["accounts"]] == [
            accounts["feishu:cli_keep"]
        ]
        text = path.read_text(encoding="utf-8")
        assert "cli_old" not in text and '"old"' not in text
        assert "FEISHU_GONE_ID" not in text and "gone-secret" not in text
        assert "${FEISHU_KEEP_ID}" in text and "${FEISHU_KEEP_SECRET}" in text
        assert kv.get("profile:lark:cli_old") is None
        assert kv.get("targets:lark:cli_old") is None
        assert kv.get("profile:feishu:cli_keep") == {"kept": True}
    assert [row.record.id for row in RoleStore(tmp_path).accounts.list()] == [
        accounts["feishu:cli_keep"]
    ]


@pytest.mark.asyncio
async def test_delete_hook_closes_the_websocket_before_purging() -> None:
    handlers: list[Any] = []
    channels: list[Any] = []
    kv: dict[str, Any] = {"profile:feishu:cli_a": {}, "targets:feishu:cli_a": {}}
    app = {"app_id": "cli_a", "app_secret": "s", "role_id": "mira"}
    ctx = SimpleNamespace(
        config=SimpleNamespace(
            as_dict=lambda: {"accounts": [app]},
            raw_as_dict=lambda: {"accounts": [app]},
        ),
        kv=SimpleNamespace(
            get=lambda key, default: kv.get(key, default),
            delete=lambda key: kv.pop(key, None),
        ),
        rpc=SimpleNamespace(register=lambda *args, **kwargs: None),
        accounts=SimpleNamespace(
            register_configured=lambda **kwargs: SimpleNamespace(
                record=SimpleNamespace(id="account-a")
            ),
            read_config_accounts=lambda reader: None,
            report=lambda *args, **kwargs: None,
            on_delete=handlers.append,
        ),
        channels=SimpleNamespace(add=channels.append),
        manifest=SimpleNamespace(channel_chat_types=lambda name: ()),
    )
    await setup(ctx)
    [channel] = channels
    order: list[str] = []
    channel.stop = AsyncMock(side_effect=lambda: order.append(f"stop:{len(kv)}"))

    plan = handlers[0]("feishu:cli_a")

    # Planning is side-effect free; disconnect closes before purge deletes.
    assert plan.plugin_config == {"accounts": []}
    assert order == [] and len(kv) == 2
    await plan.disconnect()
    await plan.purge()
    assert order == ["stop:2"]
    assert kv == {}
    assert channel._accounts is None
    repeated = handlers[0]("feishu:cli_a")
    await repeated.disconnect()
    await repeated.purge()
    assert channel.stop.await_count == 1
    assert repeated.plugin_config == {"accounts": []}
