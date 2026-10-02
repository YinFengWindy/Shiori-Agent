"""Telegram Bots live in plugin storage; adding and deleting never touch config.toml."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from shiori_sdk.testing.bridge import plugin_bridge_request
from telegram import Bot

from core.roles.store import RoleStore

_RULES = {
    "private_enabled": False,
    "group_enabled": True,
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
    monkeypatch.setattr(
        Bot,
        "get_user_profile_photos",
        AsyncMock(return_value=SimpleNamespace(photos=())),
    )


def _roles(tmp_path, *role_ids: str) -> None:
    roles = RoleStore(tmp_path)
    for role_id in role_ids:
        roles.create_role(role_id=role_id, name=role_id, system_prompt="m")


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

        deleted = await plugin_bridge_request(
            service,
            "accounts.delete",
            {"account_id": "telegram:111", "role_id": "mira"},
        )
        assert deleted.error is None, deleted.error
        after = await plugin_bridge_request(service, "accounts.list")
        assert after.payload["accounts"] == []
        assert path.read_text(encoding="utf-8") == before

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
async def test_bots_of_a_role_deleted_while_unloaded_are_removed_on_load(
    plugin_runtime, tmp_path, telegram_identity
):
    _roles(tmp_path, "mira", "gone", "third")
    async with plugin_runtime(("telegram",)) as (service, _path):
        for role_id, token in (("gone", "1:a"), ("mira", "2:b")):
            saved = await plugin_bridge_request(
                service,
                "plugin.telegram.bot.save",
                {"role_id": role_id, "token": token},
            )
            assert saved.error is None, saved.error

        async def set_enabled(enabled: bool) -> None:
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

        await set_enabled(False)
        # The unloaded plugin is not asked to clean up the role's Bot.
        removed = await plugin_bridge_request(
            service, "roles.delete", {"role_id": "gone"}
        )
        assert removed.error is None, removed.error
        assert removed.payload["deleted_accounts"] == []
        await set_enabled(True)

        listed = await plugin_bridge_request(service, "accounts.list")
        assert [row["id"] for row in listed.payload["accounts"]] == ["telegram:2"]
        # The orphaned Bot's record was purged, so another role can add it.
        again = await plugin_bridge_request(
            service, "plugin.telegram.bot.save", {"role_id": "third", "token": "1:a"}
        )
        assert again.error is None, again.error
        assert again.payload == {"account_id": "telegram:1"}
