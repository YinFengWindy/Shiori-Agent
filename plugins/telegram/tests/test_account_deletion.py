"""Deleting a Telegram Bot stops polling, purges caches, and drops its Token."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from shiori_plugin_testkit.bridge import plugin_bridge_request

from agent.plugin_host.kv import PluginKVStore
from agent.plugin_host.plugin_data import plugin_data_dir
from core.roles.store import RoleStore
from plugins.telegram.backend.account_deletion import (
    TelegramAccountDeletion,
    config_without_bot,
)
from plugins.telegram.backend.channel.lifecycle import TelegramChannel


def test_config_without_bot_keeps_other_bots_and_clears_the_legacy_token():
    raw = {
        "token": "${TG_LEGACY}",
        "bots": [
            {"ref": "first", "token": "1:a", "enabled": True},
            {"ref": "second", "token": "${TG_SECOND}", "enabled": False},
        ],
    }
    assert config_without_bot(raw, "first") == {
        "token": "${TG_LEGACY}",
        "bots": [{"ref": "second", "token": "${TG_SECOND}", "enabled": False}],
    }
    assert config_without_bot(raw, "legacy") == {**raw, "token": ""}
    assert config_without_bot(raw, "missing") is None
    assert config_without_bot({"token": "", "bots": []}, "legacy") is None


@pytest.mark.asyncio
async def test_retired_bot_stops_polling_before_caches_are_purged(tmp_path):
    store = PluginKVStore(tmp_path / "kv.json")
    for key in ("known_chats:first", "identity:first", "identity:other"):
        store.set(key, {"cached": True})
    purged_before_stop: list[bool] = []
    channel = Mock(spec=TelegramChannel)
    channel.retire = AsyncMock(
        side_effect=lambda: purged_before_stop.append(
            store.get("identity:first") is None
        )
    )
    channels = {"first": channel}
    deletion = TelegramAccountDeletion(
        channels, store, {"bots": [{"ref": "first", "token": "1:a"}]}
    )

    cleanup = await deletion("first")

    assert purged_before_stop == [False]
    assert channels == {}
    assert store.get("known_chats:first") is None
    assert store.get("identity:first") is None
    assert store.get("identity:other") == {"cached": True}
    assert cleanup.plugin_config == {"bots": []}
    retried = await deletion("first")
    channel.retire.assert_awaited_once()
    assert retried.plugin_config == {"bots": []}


@pytest.mark.asyncio
async def test_retire_reports_offline_once_and_never_after():
    accounts = Mock()
    known = Mock()
    channel = TelegramChannel(
        "123:abc", config_ref="first", accounts=accounts, known_store=known
    )
    channel._account_id = "account-1"

    await channel.retire()
    await channel.stop()

    accounts.report.assert_called_once()
    assert accounts.report.call_args.kwargs["connection"] == "offline"
    channel._remember_chat(
        SimpleNamespace(id=1, type="private"), None, SimpleNamespace()
    )
    known.set.assert_not_called()


@pytest.mark.asyncio
async def test_deleting_a_bot_removes_token_caches_and_host_record(
    plugin_runtime, tmp_path, monkeypatch
):
    monkeypatch.setenv("TG_KEEP_TOKEN", "222:keep")
    RoleStore(tmp_path).create_role(role_id="mira", name="Mira", system_prompt="m")
    config = (
        "\n[plugins.telegram]\n"
        '[[plugins.telegram.bots]]\nref = "gone"\ntoken = "111:gone"\n'
        '[[plugins.telegram.bots]]\nref = "keep"\ntoken = "${TG_KEEP_TOKEN}"\n'
    )
    async with plugin_runtime(("telegram",), config) as (service, path):
        listed = await plugin_bridge_request(service, "accounts.list")
        accounts = {row["config_ref"]: row["id"] for row in listed.payload["accounts"]}
        kv = PluginKVStore(plugin_data_dir(tmp_path, "telegram") / "kv.json")
        for ref in ("gone", "keep"):
            kv.set(f"known_chats:{ref}", {"1": {"chat_id": "1"}})
            kv.set(f"identity:{ref}", {"bot_id": ref})
        assigned = await plugin_bridge_request(
            service,
            "accounts.assign",
            {"account_id": accounts["gone"], "role_id": "mira"},
        )
        assert assigned.error is None, assigned.error

        deleted = await plugin_bridge_request(
            service,
            "accounts.delete",
            {"account_id": accounts["gone"], "role_id": "mira"},
        )

        assert deleted.error is None, deleted.error
        after = await plugin_bridge_request(service, "accounts.list")
        assert [row["id"] for row in after.payload["accounts"]] == [accounts["keep"]]
        text = path.read_text(encoding="utf-8")
        assert "111:gone" not in text and '"gone"' not in text
        assert "${TG_KEEP_TOKEN}" in text
        assert kv.get("known_chats:gone") is None
        assert kv.get("identity:gone") is None
        assert kv.get("identity:keep") == {"bot_id": "keep"}
        again = await plugin_bridge_request(
            service,
            "accounts.delete",
            {"account_id": accounts["gone"], "role_id": "mira"},
        )
        assert again.error is not None and again.error.code == "account_not_found"
    assert [row.record.id for row in RoleStore(tmp_path).accounts.list()] == [
        accounts["keep"]
    ]
