"""Bot policy through SDK account, storage and group capabilities."""

from pathlib import Path
from unittest.mock import AsyncMock
import pytest
from shiori_sdk.testing.channel_context import FakeChannelPluginContext
from shiori_sdk.accounts import AccountResponseRules
from shiori_sdk.accounts.models import AccountSnapshot
from plugins.telegram.backend.bots import TelegramBots
from plugins.telegram.backend.credentials import TelegramBotStore


@pytest.mark.asyncio
async def test_save_disconnect_and_delete_preserve_bot_owned_record(
    tmp_path, monkeypatch
):
    ctx = FakeChannelPluginContext("telegram", Path(__file__).resolve().parents[1])
    group = ctx.channels.group("telegram")
    store = TelegramBotStore(ctx.kv)
    bots = TelegramBots(ctx.as_capability(), store, group)
    monkeypatch.setattr(bots, "verify_token", AsyncMock(return_value={"bot_id": "123"}))
    try:
        assert await bots.save({"role_id": "mira", "token": "123:secret"}) == {
            "account_id": "telegram:123"
        }
        assert group.member("123") is not None
        # The Token is kept verbatim in the Bot's own record.
        assert store.list() == [
            {
                "ref": "123",
                "bot_id": "123",
                "token": "123:secret",
                "enabled": True,
                "role_id": "mira",
            }
        ]
        with pytest.raises(ValueError, match="已添加"):
            await bots.save({"role_id": "mira", "token": "123:other"})
        await bots.disconnect({"account_id": "telegram:123", "role_id": "mira"})
        assert group.member("123") is None and not store.get("123")["enabled"]
        for key in ("known_chats", "identity", "avatar"):
            ctx.kv.set(f"{key}:123", {"cached": True})
        plan = bots.delete_plan("123")
        await plan.disconnect()
        await plan.purge()
        assert store.list() == []
        assert [
            ctx.kv.get(f"{key}:123") for key in ("known_chats", "identity", "avatar")
        ] == [None, None, None]
        # The same Bot added again keeps its account ID and member channel.
        assert await bots.save({"role_id": "mira", "token": "123:again"}) == {
            "account_id": "telegram:123"
        }
        assert group.member("123") is not None
    finally:
        await group.stop()
        await ctx.aclose()


_AVATAR = "data:image/png;base64,iVBORw0KGgo="


@pytest.mark.asyncio
async def test_load_runs_saved_bots_and_skips_refused_or_orphaned_ones() -> None:
    ctx = FakeChannelPluginContext("telegram", Path(__file__).resolve().parents[1])
    ctx.accounts.available_roles = {"mira", "other"}
    rules = AccountResponseRules(private_enabled=False, blocked_sender_ids=("troll",))
    ctx.kv.set(
        "bots",
        [
            {"ref": "1", "bot_id": "1", "token": "1:a", "role_id": "mira"},
            # The host refuses a second Bot for the same role.
            {"ref": "2", "bot_id": "2", "token": "2:b", "role_id": "mira"},
            # Saved offline: registered with its stored photo, never connected.
            {
                "ref": "3",
                "bot_id": "3",
                "token": "3:c",
                "role_id": "other",
                "enabled": False,
                "response_rules": {
                    "private_enabled": False,
                    "group_enabled": True,
                    "blocked_sender_ids": ["troll"],
                },
            },
            # Its role was deleted while the plugin was not loaded.
            {"ref": "4", "bot_id": "4", "token": "4:d", "role_id": "gone"},
        ],
    )
    ctx.kv.set("avatar:3", _AVATAR)
    ctx.kv.set("identity:4", {"bot_id": "4"})
    register_saved = ctx.accounts.register_saved

    def refuse_second(**kwargs: object) -> AccountSnapshot | None:
        if kwargs["config_ref"] == "2":
            return None
        return register_saved(**kwargs)  # type: ignore[arg-type]

    ctx.accounts.register_saved = refuse_second  # type: ignore[method-assign]
    store = TelegramBotStore(ctx.kv)
    group = ctx.channels.group("telegram")
    bots = TelegramBots(ctx.as_capability(), store, group)
    try:
        await bots.load()

        assert group.member_channel("telegram_1") is not None
        assert group.member("2") is None and group.member("3") is None
        assert {
            account_id: (snapshot.connection, snapshot.record.avatar_url)
            for account_id, snapshot in ctx.accounts.records.items()
        } == {"telegram:1": ("unknown", ""), "telegram:3": ("offline", _AVATAR)}
        assert ctx.accounts.records["telegram:3"].record.response_rules == rules
        assert [row["ref"] for row in store.list()] == ["1", "2", "3"]
        assert ctx.kv.get("identity:4") is None
    finally:
        await group.stop()
        await ctx.aclose()


@pytest.mark.asyncio
async def test_rules_edited_on_the_host_are_saved_with_the_bot() -> None:
    ctx = FakeChannelPluginContext("telegram", Path(__file__).resolve().parents[1])
    ctx.kv.set(
        "bots",
        [
            {
                "ref": "1",
                "bot_id": "1",
                "token": "1:a",
                "role_id": "mira",
                "enabled": False,
            }
        ],
    )
    store = TelegramBotStore(ctx.kv)
    group = ctx.channels.group("telegram")
    bots = TelegramBots(ctx.as_capability(), store, group)
    rules = AccountResponseRules(private_enabled=False, blocked_sender_ids=("troll",))
    try:
        bots.save_rules("1", rules)
        restarted = FakeChannelPluginContext(
            "telegram", Path(__file__).resolve().parents[1]
        )
        restarted.kv = ctx.kv
        reloaded = TelegramBots(
            restarted.as_capability(),
            TelegramBotStore(restarted.kv),
            restarted.channels.group("telegram"),
        )
        await reloaded.load()
        [snapshot] = restarted.accounts.records.values()
        assert snapshot.record.response_rules == rules
        await restarted.aclose()
    finally:
        await group.stop()
        await ctx.aclose()
