"""Telegram usernames identify private delivery targets, never group members."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from telegram.error import InvalidToken, NetworkError, TelegramError
from telegram.ext import ExtBot

from plugins.telegram.backend.channel.lifecycle import TelegramChannel
from plugins.telegram.backend.channel.polling import ObservedBot
from shiori_sdk.testing.storage import FakeKV


@pytest.mark.asyncio
async def test_username_index_rejects_group_targets_live_and_on_rebuild():
    from shiori_sdk.testing.channel_sessions import FakeChannelSessions

    sessions = FakeChannelSessions()
    for chat_id, username in (("123", "alice"), ("-1001", "alice"), ("-1002", "bob")):
        sessions.get_or_create(f"telegram:{chat_id}").metadata["username"] = username
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
    store = FakeKV()
    first = TelegramChannel.__new__(TelegramChannel)
    first._known_store, first._config_ref = store, "first"
    second = TelegramChannel.__new__(TelegramChannel)
    second._known_store, second._config_ref = store, "second"
    chat = SimpleNamespace(id=-1001, type="supergroup", title="Forum")
    user = SimpleNamespace(id=11, username="member")
    first._remember_chat(chat, user, SimpleNamespace(message_thread_id=42))
    first._remember_chat(chat, user, SimpleNamespace(message_thread_id=53))
    second._remember_chat(chat, user, SimpleNamespace(message_thread_id=7))
    first_known = store.get("known_chats:first")
    second_known = store.get("known_chats:second")
    assert isinstance(first_known, dict) and isinstance(second_known, dict)
    assert first_known["-1001"]["topics"] == [42, 53]
    assert second_known["-1001"]["topics"] == [7]
    assert first_known["-1001"]["username"] == ""


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
        ),
        get_user_profile_photos=AsyncMock(return_value=SimpleNamespace(photos=())),
    )
    channel._app = SimpleNamespace(
        bot=bot,
        initialize=AsyncMock(),
        start=AsyncMock(),
        updater=SimpleNamespace(start_polling=AsyncMock()),
    )
    await channel.start()
    assert channel._avatar_task is not None
    await channel._avatar_task
    assert channel.status()["connected"] is True
    assert channel.status()["account"] == "@first_bot"
    assert [call.kwargs["connection"] for call in accounts.report.call_args_list] == [
        "connecting",
        "online",
    ]
    assert any(
        call.kwargs.get("display_name") == "First Bot"
        for call in accounts.register.call_args_list
    )
    channel._known_store.set.assert_any_call(
        "identity:first",
        {"bot_id": "123", "name": "First Bot", "username": "first_bot"},
    )
    assert channel.via_account() == {
        "platform": "telegram",
        "platform_account_id": "123",
        "display_name": "First Bot",
        "prefix": "Telegram 机器人「First Bot」（@first_bot）",
    }


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


@pytest.mark.asyncio
async def test_transient_polling_error_waits_for_actual_inbound_recovery():
    channel = TelegramChannel("123:abc", name="telegram_first", config_ref="first")
    channel._accounts = Mock()
    channel._account_id = "account-1"
    channel._online = True
    channel._app = SimpleNamespace(
        updater=SimpleNamespace(running=True),
        bot=SimpleNamespace(get_me=AsyncMock(return_value=SimpleNamespace(id=123))),
    )
    channel._on_polling_error(NetworkError("temporary"))
    assert channel._online is False
    assert channel.can_send() is True
    assert channel._accounts.report.call_args.kwargs["connection"] == "connecting"
    channel._on_polling_error(TelegramError("permanent polling failure"))
    assert channel._online is False
    assert channel._accounts.report.call_args.kwargs["connection"] == "error"
    channel.mark_online()
    assert channel._online is True
    assert channel._accounts.report.call_args.kwargs["connection"] == "online"
    channel._polling_conflict_task = Mock()
    channel._on_polling_error(TelegramError("another failure"))
    channel.mark_online()
    assert channel._online is False


@pytest.mark.asyncio
async def test_channel_recovers_on_empty_successful_poll(monkeypatch):
    monkeypatch.setattr(ExtBot, "get_updates", AsyncMock(return_value=()))
    accounts = Mock()
    channel = TelegramChannel(
        "123:abc", name="telegram_first", config_ref="first", accounts=accounts
    )
    bot = channel.bot
    assert isinstance(bot, ObservedBot)
    channel._account_id = "account-1"
    channel._online = False
    channel._app = Mock(updater=Mock(running=True))
    await bot.get_updates()
    assert channel._online is True
    assert accounts.report.call_args.kwargs["connection"] == "online"


@pytest.mark.asyncio
@pytest.mark.parametrize("fetch_ok", [False, True])
async def test_bot_photo_is_stored_and_kept_when_its_refresh_fails(tmp_path, fetch_ok):
    png = bytes.fromhex("89504e470d0a1a0a")
    old = "data:image/png;base64,AAAA"
    store = FakeKV()
    store.set("avatar:first", old)
    channel = TelegramChannel("123:abc", name="telegram_first", config_ref="first")
    accounts = Mock()
    accounts.register.return_value = SimpleNamespace(
        record=SimpleNamespace(id="account-1")
    )
    channel._accounts = accounts
    channel._known_store = store
    channel._intake = Mock()
    channel._bind_runtime = Mock()
    channel._rebuild_user_map = Mock()
    channel._register_bot_commands = AsyncMock()
    photo = SimpleNamespace(file_id="small")
    bot = SimpleNamespace(
        get_me=AsyncMock(
            return_value=SimpleNamespace(id=123, full_name="Bot", username="bot")
        ),
        get_user_profile_photos=(
            AsyncMock(return_value=SimpleNamespace(photos=((photo,),)))
            if fetch_ok
            else AsyncMock(side_effect=NetworkError("offline"))
        ),
        get_file=AsyncMock(
            return_value=SimpleNamespace(
                download_as_bytearray=AsyncMock(return_value=bytearray(png))
            )
        ),
    )
    channel._app = SimpleNamespace(
        bot=bot,
        initialize=AsyncMock(),
        start=AsyncMock(),
        updater=SimpleNamespace(start_polling=AsyncMock()),
    )

    await channel.start()
    assert channel._avatar_task is not None
    await channel._avatar_task

    bot.get_user_profile_photos.assert_awaited_once_with(123, limit=1)
    fresh = "data:image/png;base64,iVBORw0KGgo="
    assert store.get("avatar:first") == (fresh if fetch_ok else old)
    avatars = [
        call.kwargs["avatar_url"]
        for call in accounts.register.call_args_list
        if "avatar_url" in call.kwargs
    ]
    assert avatars == ([fresh] if fetch_ok else [])
