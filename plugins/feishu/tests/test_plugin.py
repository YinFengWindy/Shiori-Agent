from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from typing import Any

import pytest
from shiori_plugin_testkit.packages import stage_plugin_package
from shiori_plugin_testkit.bridge import plugin_bridge_request

from agent.plugin_host import HostServices, PluginKernel, load_manifest
from bus.event_bus import EventBus
from core.roles.store import RoleStore

PLUGIN_DIR = Path(__file__).resolve().parents[1]


def _load_feishu_channels(
    plugin_configs: dict[str, dict[str, Any]] | None = None,
) -> tuple[int, list[Any]]:
    with tempfile.TemporaryDirectory() as tmp:
        stage_plugin_package(PLUGIN_DIR, Path(tmp) / "feishu")
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
    assert channel.configuration_key[:5] == (
        "feishu",
        "feishu",
        "cli_a",
        "s",
        "https://open.larksuite.com",
    )


def test_two_regional_apps_register_distinct_accounts_and_channels() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        stage_plugin_package(PLUGIN_DIR, root / "feishu")
        roles = RoleStore(root)
        kernel = PluginKernel(
            [root],
            services=HostServices(
                event_bus=EventBus(),
                workspace=root,
                role_store=roles,
                plugin_configs={
                    "feishu": {
                        "accounts": [
                            {
                                "app_id": "cli_a",
                                "app_secret": "first",
                                "domain": "feishu",
                            },
                            {
                                "app_id": "cli_b",
                                "app_secret": "second",
                                "domain": "lark",
                            },
                        ]
                    }
                },
            ),
        )
        asyncio.run(kernel.load_all())

        assert [channel.name for channel in kernel.channels] == [
            "feishu",
            "feishu:lark:cli_b",
        ]
        assert {row.record.platform_account_id for row in roles.accounts.list()} == {
            "feishu:cli_a",
            "lark:cli_b",
        }
        assert all(row.connection == "connecting" for row in roles.accounts.list())
        assert all("secret" not in str(row) for row in roles.accounts.list())


def test_invalid_config_fails_the_plugin_and_rolls_back() -> None:
    loaded, channels = _load_feishu_channels(
        {"feishu": {"app_id": "a", "app_secret": "s", "domain": "https://evil"}}
    )

    assert (loaded, channels) == (0, [])


def test_one_unresolved_secret_does_not_disable_another_account() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        stage_plugin_package(PLUGIN_DIR, root / "feishu")
        roles = RoleStore(root)
        kernel = PluginKernel(
            [root],
            services=HostServices(
                event_bus=EventBus(),
                workspace=root,
                role_store=roles,
                plugin_configs={
                    "feishu": {
                        "accounts": [
                            {
                                "app_id": "cli_ready",
                                "app_secret": "ready",
                                "domain": "feishu",
                            },
                            {
                                "app_id": "cli_missing",
                                "app_secret": "${MISSING_SECRET}",
                                "domain": "lark",
                            },
                        ]
                    }
                },
            ),
        )
        asyncio.run(kernel.load_all())
        assert kernel.loaded_count == 1
        assert [channel.name for channel in kernel.channels] == ["feishu"]
        states = {
            row.record.platform_account_id: row.connection
            for row in roles.accounts.list()
        }
        assert states == {
            "feishu:cli_ready": "connecting",
            "lark:cli_missing": "login_required",
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
