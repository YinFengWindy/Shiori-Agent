"""Telegram usernames identify private delivery targets, never group members."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from plugins.telegram.backend.channel.lifecycle import TelegramChannel


@pytest.mark.asyncio
async def test_username_index_rejects_group_targets_live_and_on_rebuild():
    sessions = SimpleNamespace(
        get_channel_metadata=lambda _: [
            {"chat_id": "123", "metadata": {"username": "alice"}},
            {"chat_id": "-1001", "metadata": {"username": "alice"}},
            {"chat_id": "-1002", "metadata": {"username": "bob"}},
        ],
    )
    channel = TelegramChannel.__new__(TelegramChannel)
    # Bind the real index through the same lifecycle path used at startup.
    channel._channel = "telegram"
    channel._channel_hub = None
    channel._bind_session_manager(sessions)
    channel._rebuild_user_map()
    assert channel.user_map == {"alice": "123"}
    channel._identity_index.remember = AsyncMock()
    await channel._remember_username("-1003", "alice")
    channel._identity_index.remember.assert_not_awaited()
    await channel._remember_username("123", "alice")
    channel._identity_index.remember.assert_awaited_once_with("alice", "123")
