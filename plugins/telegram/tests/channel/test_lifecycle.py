"""Telegram usernames identify private delivery targets, never group members."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from telegram.error import InvalidToken

from plugins.telegram.backend.channel.lifecycle import TelegramChannel
from agent.plugin_host.kv import PluginKVStore


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


def test_observed_topics_are_private_to_the_receiving_bot(tmp_path):
    store = PluginKVStore(tmp_path / "telegram.json")
    first = TelegramChannel.__new__(TelegramChannel)
    first._known_store, first._config_ref = store, "first"
    second = TelegramChannel.__new__(TelegramChannel)
    second._known_store, second._config_ref = store, "second"
    chat = SimpleNamespace(id=-1001, type="supergroup", title="Forum")
    user = SimpleNamespace(id=11, username="member")
    first._remember_chat(chat, user, SimpleNamespace(message_thread_id=42))
    first._remember_chat(chat, user, SimpleNamespace(message_thread_id=53))
    second._remember_chat(chat, user, SimpleNamespace(message_thread_id=7))
    assert store.get("known_chats:first")["-1001"]["topics"] == [42, 53]
    assert store.get("known_chats:second")["-1001"]["topics"] == [7]
    assert store.get("known_chats:first")["-1001"]["username"] == ""


@pytest.mark.asyncio
async def test_verified_identity_and_polling_status_are_account_scoped():
    channel = TelegramChannel("123:abc", name="telegram_first", config_ref="first")
    accounts = Mock()
    accounts.register.return_value = SimpleNamespace(
        record=SimpleNamespace(id="account-1")
    )
    channel._accounts = accounts
    channel._known_store = Mock()
    channel._intake = Mock()
    channel._bind_runtime = Mock()
    channel._rebuild_user_map = Mock()
    channel._register_bot_commands = AsyncMock()
    bot = SimpleNamespace(
        get_me=AsyncMock(
            return_value=SimpleNamespace(
                id=123,
                full_name="First Bot",
                username="first_bot",
            )
        )
    )
    channel._app = SimpleNamespace(
        bot=bot,
        initialize=AsyncMock(),
        start=AsyncMock(),
        updater=SimpleNamespace(start_polling=AsyncMock()),
    )
    await channel.start()
    assert channel.status()["connected"] is True
    assert channel.status()["account"] == "@first_bot"
    assert [call.kwargs["connection"] for call in accounts.report.call_args_list] == [
        "connecting",
        "online",
    ]
    assert accounts.register.call_args_list[-1].kwargs["display_name"] == "First Bot"
    channel._known_store.set.assert_called_once_with(
        "identity:first",
        {"bot_id": "123", "name": "First Bot", "username": "first_bot"},
    )


@pytest.mark.asyncio
async def test_auth_failure_reports_only_this_account_and_cleans_up():
    channel = TelegramChannel("123:abc", name="telegram_first", config_ref="first")
    accounts = Mock()
    accounts.register.return_value = SimpleNamespace(
        record=SimpleNamespace(id="account-1")
    )
    channel._accounts = accounts
    channel._intake = Mock(close=AsyncMock())
    channel._bind_runtime = Mock()
    channel._unbind_runtime = Mock()
    channel._rebuild_user_map = Mock()
    channel._app = SimpleNamespace(
        initialize=AsyncMock(side_effect=InvalidToken("bad token")),
        running=False,
        updater=SimpleNamespace(running=False),
        shutdown=AsyncMock(),
    )
    with pytest.raises(InvalidToken):
        await channel.start()
    assert [call.kwargs["connection"] for call in accounts.report.call_args_list] == [
        "connecting",
        "login_required",
    ]
    channel._app.shutdown.assert_awaited_once()
    channel._unbind_runtime.assert_called_once()
