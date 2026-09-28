"""Telegram Bots live in plugin storage; adding and deleting never touch config.toml."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from shiori_plugin_testkit.bridge import plugin_bridge_request
from telegram import Bot

from agent.plugin_host.kv import PluginKVStore
from agent.plugin_host.plugin_data import plugin_data_dir
from core.roles.store import RoleStore

_RULES = {
    "private_enabled": False,
    "group_enabled": True,
    "require_mention": False,
    "blocked_sender_ids": ["troll"],
}


@pytest.fixture
def telegram_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    """Token verification answers with the Bot ID the Token starts with."""

    async def get_me(bot: Bot, *_args, **_kwargs):
        bot_id = int(bot.token.split(":", 1)[0])
        return SimpleNamespace(id=bot_id, full_name=f"Bot {bot_id}", username="")

    monkeypatch.setattr(Bot, "initialize", AsyncMock())
    monkeypatch.setattr(Bot, "shutdown", AsyncMock())
    monkeypatch.setattr(Bot, "get_me", get_me)


def _roles(tmp_path, *role_ids: str) -> None:
    roles = RoleStore(tmp_path)
    for role_id in role_ids:
        roles.create_role(role_id=role_id, name=role_id, system_prompt="m")


def _kv(tmp_path) -> PluginKVStore:
    return PluginKVStore(plugin_data_dir(tmp_path, "telegram") / "kv.json")


@pytest.mark.asyncio
async def test_bots_are_added_and_deleted_without_writing_host_config(
    plugin_runtime, tmp_path, telegram_identity
):
    _roles(tmp_path, "mira")
    async with plugin_runtime(("telegram",)) as (service, path):
        before = path.read_text(encoding="utf-8")
        saved = await plugin_bridge_request(
            service, "plugin.telegram.bot.save", {"role_id": "mira", "token": "111:a"}
        )
        assert saved.error is None, saved.error
        assert saved.payload == {"account_id": "telegram:111"}
        listed = await plugin_bridge_request(service, "accounts.list")
        assert [(row["id"], row["role_id"]) for row in listed.payload["accounts"]] == [
            ("telegram:111", "mira")
        ]
        assert path.read_text(encoding="utf-8") == before
        assert "111:a" not in before
        kv = _kv(tmp_path)
        assert kv.get("bots") == [
            {
                "ref": "111",
                "bot_id": "111",
                "token": "111:a",
                "enabled": True,
                "role_id": "mira",
            }
        ]
        kv.set("known_chats:111", {"1": {"chat_id": "1"}})
        kv.set("identity:111", {"bot_id": "111"})

        deleted = await plugin_bridge_request(
            service,
            "accounts.delete",
            {"account_id": "telegram:111", "role_id": "mira"},
        )
        assert deleted.error is None, deleted.error
        after = await plugin_bridge_request(service, "accounts.list")
        assert after.payload["accounts"] == []
        assert path.read_text(encoding="utf-8") == before
        assert kv.get("bots") == []
        assert kv.get("known_chats:111") is None
        assert kv.get("identity:111") is None

        # The same Bot added again gets the same account ID back.
        again = await plugin_bridge_request(
            service, "plugin.telegram.bot.save", {"role_id": "mira", "token": "111:b"}
        )
        assert again.payload == {"account_id": "telegram:111"}


@pytest.mark.asyncio
async def test_rules_survive_a_plugin_restart_and_disabled_bots_are_absent(
    plugin_runtime, tmp_path, telegram_identity
):
    _roles(tmp_path, "mira")
    async with plugin_runtime(("telegram",)) as (service, _path):
        await plugin_bridge_request(
            service, "plugin.telegram.bot.save", {"role_id": "mira", "token": "111:a"}
        )
        changed = await plugin_bridge_request(
            service,
            "accounts.rules.set",
            {"account_id": "telegram:111", "response_rules": _RULES},
        )
        assert changed.error is None, changed.error
        for enabled in (False, True):
            toggled = await plugin_bridge_request(
                service,
                "plugins.setEnabled",
                {
                    "plugin_id": "telegram",
                    "enabled": enabled,
                    "operation_id": f"telegram-{enabled}",
                },
            )
            assert toggled.error is None, toggled.error
            listed = await plugin_bridge_request(service, "accounts.list")
            assert [row["response_rules"] for row in listed.payload["accounts"]] == (
                [_RULES] if enabled else []
            )


@pytest.mark.asyncio
async def test_bots_of_a_deleted_role_are_removed_on_load(plugin_runtime, tmp_path):
    _roles(tmp_path, "mira")
    kv = _kv(tmp_path)
    kv.set(
        "bots",
        [
            {"ref": "1", "bot_id": "1", "token": "1:a", "role_id": "gone"},
            {"ref": "2", "bot_id": "2", "token": "2:b", "role_id": "mira"},
        ],
    )
    kv.set("identity:1", {"bot_id": "1"})
    async with plugin_runtime(("telegram",)) as (service, _path):
        listed = await plugin_bridge_request(service, "accounts.list")
        assert [row["id"] for row in listed.payload["accounts"]] == ["telegram:2"]
    assert [row["ref"] for row in kv.get("bots")] == ["2"]
    assert kv.get("identity:1") is None
