"""Inbound messages retain Telegram's actual sender and topic."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from plugins.telegram.backend.channel.inbound import _InboundMixin
from shiori_sdk.testing.channel_hub import FakeChannelHub
from shiori_sdk.testing.channel_services import FakeMessageBus


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
    channel._account_id = "telegram:123"
    channel.via_account = Mock(return_value={"platform_account_id": "123"})
    sender_chat = SimpleNamespace(id=-1009, username="anonymous", title="频道")
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
    assert sent.metadata["account_id"] == "telegram:123"
    assert sent.metadata["via_account"] == {"platform_account_id": "123"}
    assert sent.metadata["group_name"] == "Forum"
    assert sent.metadata["sender_name"] == "频道"
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


@pytest.mark.asyncio
async def test_private_pairing_code_binds_with_platform_scope_only_in_private_chats():
    from shiori_sdk.messages import InboundMessage

    hub = FakeChannelHub(pairing_code="PAIR1234")
    bus = FakeMessageBus()
    channel = _InboundMixin()
    channel._channel_hub = hub
    channel.mark_online = Mock()
    channel.send = AsyncMock()
    channel._require_bus = Mock(return_value=bus)

    def inbound(chat_id: str, chat_type: str) -> InboundMessage:
        return InboundMessage(
            channel="telegram_bot",
            sender="77",
            chat_id=chat_id,
            content="PAIR1234",
            # The group message @s the Bot, so the host starts a turn with it.
            metadata={
                "account_id": "telegram:1",
                "chat_type": chat_type,
                "mentioned": True,
            },
        )

    await channel._accept_inbound(inbound("77", "private"))
    await channel._accept_inbound(inbound("-1001", "supergroup"))

    assert hub.pairings == [("77", "PAIR1234", "platform")]
    channel.send.assert_awaited_once_with("77", "已绑定")
    [published] = bus.inbound
    assert published.chat_id == "-1001"


@pytest.mark.asyncio
async def test_received_message_refreshes_its_sender_and_chat_avatars():
    from shiori_sdk.messages import InboundMessage

    channel = _InboundMixin()
    channel._avatars = Mock(refresh=Mock(return_value=None))
    channel.bot = Mock()
    channel._channel_hub = FakeChannelHub()
    channel.mark_online = Mock()
    channel._require_bus = Mock(return_value=FakeMessageBus())

    await channel._accept_inbound(
        InboundMessage(
            channel="telegram_bot",
            sender="77",
            chat_id="-1001",
            content="hello",
            metadata={
                "account_id": "telegram:1",
                "chat_type": "supergroup",
                "mentioned": True,
            },
        )
    )

    assert {call.args[:3] for call in channel._avatars.refresh.call_args_list} == {
        ("sender", "telegram_bot", "77"),
        ("chat", "telegram_bot", "-1001"),
    }
