"""Telegram account operations remain scoped to one observed Bot."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from telegram.error import Forbidden, TimedOut

from plugins.telegram.backend.account_api import TelegramAccountApi
from core.accounts.target_contract import UncertainDeliveryError


def _png(tmp_path) -> str:
    """A real PNG file on disk, as a local image path."""
    path = tmp_path / "sky.png"
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"body")
    return str(path)


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
        send_image=AsyncMock(return_value="78"),
        via_account=Mock(return_value={"platform_account_id": "123"}),
    )
    second = SimpleNamespace(
        _account_id="account-second", can_send=Mock(return_value=True), bot=Mock()
    )
    return (
        TelegramAccountApi(_bots({"first": first, "second": second}), Mock(), store),
        first,
    )


def _bots(channels):
    """The running Bots the API resolves refs and account IDs through."""

    def ref_for_account(account_id):
        for ref, channel in channels.items():
            if channel._account_id == account_id:
                return ref
        raise ValueError("Unknown Telegram Bot account")

    return SimpleNamespace(channel=channels.get, ref_for_account=ref_for_account)


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
    offline = TelegramAccountApi(_bots({}), Mock(), api._store)
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
    assert receipt["via_account"] == {"platform_account_id": "123"}
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


@pytest.mark.asyncio
async def test_missing_telegram_receipt_is_uncertain(account_api):
    api, first = account_api
    first.send.return_value = None
    with pytest.raises(UncertainDeliveryError):
        await api.account_send(
            {
                "account_id": "account-first",
                "target_kind": "private",
                "target_id": "123",
                "message": "hello",
            }
        )


@pytest.mark.asyncio
async def test_telegram_network_error_is_uncertain(account_api):
    api, first = account_api
    first.send.side_effect = TimedOut("reply lost")
    with pytest.raises(UncertainDeliveryError):
        await api.account_send(
            {
                "account_id": "account-first",
                "target_kind": "private",
                "target_id": "123",
                "message": "hello",
            }
        )


@pytest.mark.asyncio
async def test_group_send_mentions_members_but_temporary_sessions_are_refused(
    account_api,
):
    api, first = account_api
    group = {
        "account_id": "account-first",
        "target_kind": "group",
        "target_id": "-1001",
        "message": "开会",
        "mention_ids": ["902"],
    }
    await api.account_send(group)
    first.send.assert_awaited_once_with(
        "-1001", "[@902](tg://user?id=902) 开会", message_thread_id=None
    )
    with pytest.raises(ValueError, match="群临时会话"):
        await api.account_send(
            {**group, "target_kind": "group_member", "mention_ids": []}
        )
    with pytest.raises(ValueError, match="数字用户 ID"):
        await api.account_send({**group, "mention_ids": ["@someone"]})
    assert first.send.await_count == 1


@pytest.mark.asyncio
async def test_images_follow_the_text_in_the_same_topic(account_api, tmp_path):
    sky = _png(tmp_path)
    api, first = account_api
    group = {
        "account_id": "account-first",
        "target_kind": "group",
        "target_id": "-1001",
        "message": "看天空",
        "message_thread_id": 42,
        "media": [sky],
    }
    receipt = await api.account_send(group)
    assert receipt["message_id"] == "77"
    first.send.assert_awaited_once_with("-1001", "看天空", message_thread_id=42)
    first.send_image.assert_awaited_once_with("-1001", sky, message_thread_id=42)
    only_image = await api.account_send({**group, "message": ""})
    assert only_image["message_id"] == "78"
    assert first.send.await_count == 1

    # The text already reached the chat: a failed photo leaves it uncertain.
    first.send_image.side_effect = FileNotFoundError("sky.png")
    with pytest.raises(UncertainDeliveryError, match="部分送达"):
        await api.account_send(group)


@pytest.mark.asyncio
async def test_invalid_local_image_is_refused_before_any_send(account_api, tmp_path):
    api, first = account_api
    with pytest.raises(ValueError, match="图片文件不存在"):
        await api.account_send(
            {
                "account_id": "account-first",
                "target_kind": "private",
                "target_id": "123",
                "message": "看天空",
                "media": [str(tmp_path / "gone.png")],
            }
        )
    first.send.assert_not_awaited()
    first.send_image.assert_not_awaited()
