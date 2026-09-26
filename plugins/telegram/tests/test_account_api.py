"""Telegram account operations remain scoped to one observed Bot."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from telegram.error import Forbidden

from plugins.telegram.backend.account_api import TelegramAccountApi


@pytest.fixture
def account_api():
    store = Mock()
    store.get.side_effect = lambda key, default: {
        "known_chats:first": {
            "-1001": {"chat_id": "-1001", "chat_type": "group", "last_seen": "1"}
        },
        "known_chats:second": {},
        "identity:first": {
            "bot_id": "123",
            "name": "First Bot",
            "username": "first_bot",
        },
    }.get(key, default)
    first = SimpleNamespace(
        _config_ref="first",
        _account_id="account-first",
        can_send=Mock(return_value=True),
        mark_online=Mock(),
        bot=SimpleNamespace(get_chat_member=AsyncMock()),
        send=AsyncMock(return_value="77"),
    )
    second = SimpleNamespace(
        _account_id="account-second", can_send=Mock(return_value=True), bot=Mock()
    )
    return TelegramAccountApi({"first": first, "second": second}, Mock(), store), first


@pytest.mark.asyncio
async def test_known_chats_are_per_bot_and_not_a_full_directory(account_api):
    api, _ = account_api
    assert (await api.list_known({"ref": "first"}))["chats"][0]["chat_id"] == "-1001"
    assert await api.list_known({"ref": "second"}) == {
        "scope": "known_conversations",
        "chats": [],
    }
    assert await api.get_identity({"ref": "first"}) == {
        "bot_id": "123",
        "name": "First Bot",
        "username": "first_bot",
    }
    offline = TelegramAccountApi({}, Mock(), api._store)
    assert (await offline.list_known({"ref": "first"}))["chats"][0][
        "chat_id"
    ] == "-1001"


@pytest.mark.asyncio
async def test_member_lookup_requires_observed_group_and_reports_denial(account_api):
    api, first = account_api
    with pytest.raises(ValueError):
        await api.get_member({"ref": "second", "chat_id": "-1001", "user_id": "42"})
    first.bot.get_chat_member.side_effect = Forbidden("not enough rights")
    assert (
        await api.get_member(
            {
                "ref": "first",
                "chat_id": "-1001",
                "user_id": "42",
            }
        )
    )["status"] == "unavailable"


@pytest.mark.asyncio
async def test_target_send_selects_bot_and_topic(account_api):
    api, first = account_api
    receipt = await api.send_target(
        {
            "ref": "first",
            "chat_id": "-1001",
            "message_thread_id": 42,
            "text": "hi",
        }
    )
    first.send.assert_awaited_once_with("-1001", "hi", message_thread_id=42)
    assert receipt["message_id"] == "77"


@pytest.mark.asyncio
async def test_shared_account_contract_preserves_bot_and_topic(account_api):
    api, first = account_api
    known = await api.account_targets({"account_id": "account-first", "kind": "known"})
    assert known["scope"] == "known_conversations"
    receipt = await api.account_send(
        {
            "account_id": "account-first",
            "target_kind": "group",
            "target_id": "-1001",
            "message": "hello",
            "message_thread_id": 42,
        }
    )
    assert receipt["message_id"] == "77"
    first.send.assert_awaited_once_with("-1001", "hello", message_thread_id=42)
    with pytest.raises(ValueError, match="目标类型"):
        await api.account_send(
            {
                "account_id": "account-first",
                "target_kind": "private",
                "target_id": "-1001",
                "message": "hello",
            }
        )
