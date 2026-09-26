"""Inbound messages retain Telegram's actual sender and topic."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from plugins.telegram.backend.channel.inbound import _InboundMixin


@pytest.mark.asyncio
async def test_anonymous_group_message_keeps_chat_subject_and_topic():
    channel = _InboundMixin()
    channel._channel = "telegram_second"
    channel._message_deduper = Mock(seen=Mock(return_value=False))
    channel._is_sender_admitted = Mock(return_value=True)
    channel._remember_chat = Mock()
    channel._remember_username = AsyncMock()
    channel._safe_send_typing = AsyncMock()
    channel._publish_inbound = AsyncMock()
    sender_chat = SimpleNamespace(id=-1009, username="anonymous")
    update = SimpleNamespace(
        effective_message=SimpleNamespace(
            text="hello",
            message_id=11,
            message_thread_id=42,
            sender_chat=sender_chat,
            from_user=SimpleNamespace(id=1087968824, username="GroupAnonymousBot"),
            reply_to_message=None,
        ),
        effective_chat=SimpleNamespace(id=-1001, type="supergroup", title="Forum"),
        effective_user=SimpleNamespace(id=1087968824, username="GroupAnonymousBot"),
    )
    await channel._on_message(update, SimpleNamespace(bot=Mock()))
    sent = channel._publish_inbound.await_args.args[0]
    assert sent.channel == "telegram_second"
    assert sent.sender == "chat:-1009"
    assert sent.metadata["sender_kind"] == "chat"
    assert sent.metadata["message_thread_id"] == 42
    channel._is_sender_admitted.assert_called_once_with(
        update.effective_chat, sender_chat, "消息", sender_id="chat:-1009"
    )
    channel._remember_chat.assert_called_once_with(
        update.effective_chat, sender_chat, update.effective_message
    )
    channel._remember_username.assert_awaited_once_with("-1001", "anonymous")


@pytest.mark.asyncio
async def test_unbound_chat_is_observed_without_publishing_its_message():
    channel = _InboundMixin()
    channel._remember_chat = Mock()
    channel._is_sender_admitted = Mock(return_value=False)
    channel._publish_inbound = AsyncMock()
    sender = SimpleNamespace(id=9, username="member")
    message = SimpleNamespace(text="private content", from_user=sender)
    chat = SimpleNamespace(id=-1001, type="supergroup")
    update = SimpleNamespace(
        effective_message=message,
        effective_chat=chat,
        effective_user=sender,
    )
    await channel._on_message(update, SimpleNamespace(bot=Mock()))
    channel._remember_chat.assert_called_once_with(chat, sender, message)
    channel._publish_inbound.assert_not_awaited()
