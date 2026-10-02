"""Bot policy through SDK account, storage and group capabilities."""

from pathlib import Path
from unittest.mock import AsyncMock
import pytest
from shiori_sdk.testing.channel_context import FakeChannelPluginContext
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
        with pytest.raises(ValueError, match="已添加"):
            await bots.save({"role_id": "mira", "token": "123:other"})
        await bots.disconnect({"account_id": "telegram:123", "role_id": "mira"})
        assert group.member("123") is None and not store.get("123")["enabled"]
        ctx.kv.set("known_chats:123", {"1": {"chat_id": "1"}})
        plan = bots.delete_plan("123")
        await plan.disconnect()
        await plan.purge()
        assert store.list() == [] and ctx.kv.get("known_chats:123") is None
    finally:
        await group.stop()
        await ctx.aclose()
