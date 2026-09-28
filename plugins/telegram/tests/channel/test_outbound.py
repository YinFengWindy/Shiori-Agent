"""Final reply bookkeeping follows Telegram sends and retained stream messages."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from bus.events import OutboundMessage
from plugins.telegram.backend.channel.outbound import _OutboundMixin
from plugins.telegram.backend.utils import TelegramOutboundLimiter


def reply_channel(receipt):
    channel = _OutboundMixin()
    channel._app = SimpleNamespace(
        bot=SimpleNamespace(
            send_message=AsyncMock(return_value=receipt),
            edit_message_text=AsyncMock(return_value=True),
            send_photo=AsyncMock(return_value=SimpleNamespace(message_id=302)),
        )
    )
    channel._channel = "telegram"
    channel._channel_hub = Mock()
    # Receipt bookkeeping is under test, not Telegram pacing: zero intervals keep
    # chunked, media and stream-edit sends from waiting on per-chat slots.
    channel._telegram_outbound_limiter = TelegramOutboundLimiter(
        send_interval_s=0, edit_interval_s=0, global_interval_s=0
    )
    channel._has_live_messages = Mock(return_value=False)
    channel._final_thinking_text = Mock(return_value="")
    channel._active_streams = {}
    channel._reply_buffers = {}
    channel._thinking_buffers = {}
    return channel


@pytest.mark.parametrize(
    ("content", "media", "streamed", "receipt", "expected"),
    [
        ("reply", [], False, SimpleNamespace(message_id=301), "301"),
        (
            "reply",
            ["https://example.test/image"],
            False,
            SimpleNamespace(message_id=301),
            "301",
        ),
        ("", ["https://example.test/image"], False, None, "302"),
        (
            "",
            ["https://example.test/one", "https://example.test/two"],
            False,
            None,
            "302",
        ),
        ("reply", [], False, None, ""),
        ("reply" * 1000, [], False, SimpleNamespace(message_id=301), "301"),
        ("reply", [], True, SimpleNamespace(message_id=301), "301"),
    ],
)
async def test_response_records_first_retained_receipt(
    content, media, streamed, receipt, expected
):
    channel = reply_channel(receipt)
    if len(media) > 1:
        channel._app.bot.send_photo.side_effect = [
            SimpleNamespace(message_id=302),
            SimpleNamespace(message_id=399),
        ]
    if len(content) > 4096:
        channel._app.bot.send_message.side_effect = [
            SimpleNamespace(message_id=301),
            SimpleNamespace(message_id=399),
        ]
    if streamed:
        sender = channel.create_stream_sender("123")
        await sender("preview")
    message = OutboundMessage(
        channel="telegram",
        chat_id="123",
        content=content,
        media=media,
        metadata={"external_message_id": "incoming", "streamed_reply": streamed},
        committed_message_id="committed",
    )
    await channel._on_response(message)
    channel._channel_hub.mark_delivery.assert_called_once_with(
        message,
        default_channel="telegram",
        delivery_status="sent",
        external_message_id=expected,
        via_account=None,
    )
    if streamed:
        channel._app.bot.send_message.assert_awaited_once()
        channel._app.bot.edit_message_text.assert_awaited_once()
    if len(content) > 4096:
        assert channel._app.bot.send_message.await_count > 1


async def test_reply_uses_original_forum_topic() -> None:
    channel = reply_channel(SimpleNamespace(message_id=301))
    message = OutboundMessage(
        channel="telegram",
        chat_id="-1001",
        content="reply",
        metadata={"message_thread_id": 42},
        committed_message_id="committed",
    )
    await channel._on_response(message)
    assert channel._app.bot.send_message.await_args.kwargs["message_thread_id"] == 42


@pytest.mark.parametrize(
    "failure", [RuntimeError("send failed"), asyncio.CancelledError()]
)
async def test_failed_or_cancelled_send_is_never_marked_sent(failure):
    channel = reply_channel(None)
    channel._app.bot.send_message.side_effect = failure
    message = OutboundMessage(
        channel="telegram",
        chat_id="123",
        content="reply",
        metadata={"external_message_id": "incoming"},
    )
    with pytest.raises(type(failure)):
        await channel._on_response(message)
    channel._channel_hub.mark_delivery.assert_called_once_with(
        message,
        default_channel="telegram",
        delivery_status="failed",
        external_message_id="",
        via_account=None,
    )


@pytest.mark.parametrize("plain_fallback", [False, True])
@pytest.mark.parametrize(
    "failure", [RuntimeError("second chunk failed"), asyncio.CancelledError()]
)
async def test_partial_chunk_failure_retains_first_receipt(
    monkeypatch, plain_fallback, failure
):
    channel = reply_channel(None)
    channel._app.bot.send_message.side_effect = [
        SimpleNamespace(message_id=301),
        failure,
    ]
    if plain_fallback:
        monkeypatch.setattr(
            "plugins.telegram.backend.utils.convert_with_segments",
            Mock(side_effect=ValueError("invalid markdown")),
        )
    message = OutboundMessage(
        channel="telegram",
        chat_id="123",
        content="a" * 4090 + "\n" + "b" * 30,
        metadata={"external_message_id": "incoming"},
        committed_message_id="committed",
    )
    with pytest.raises(type(failure)):
        await channel._on_response(message)
    assert channel._app.bot.send_message.await_count == 2
    channel._channel_hub.mark_delivery.assert_called_once_with(
        message,
        default_channel="telegram",
        delivery_status="failed",
        external_message_id="301",
        via_account=None,
    )


async def test_failed_stream_finalization_retains_acknowledged_message():
    channel = reply_channel(SimpleNamespace(message_id=301))
    sender = channel.create_stream_sender("123")
    await sender("preview")
    channel._app.bot.edit_message_text.side_effect = RuntimeError("edit failed")
    message = OutboundMessage(
        channel="telegram",
        chat_id="123",
        content="final",
        metadata={"external_message_id": "incoming", "streamed_reply": True},
    )
    with pytest.raises(RuntimeError, match="edit failed"):
        await channel._on_response(message)
    channel._channel_hub.mark_delivery.assert_called_once_with(
        message,
        default_channel="telegram",
        delivery_status="failed",
        external_message_id="301",
        via_account=None,
    )


_VIA = {
    "platform": "telegram",
    "platform_account_id": "123",
    "display_name": "Mira Bot",
    "prefix": "Telegram 机器人「Mira Bot」（@mira_bot）",
}


async def test_group_reply_answers_its_trigger_and_mentions_chosen_members() -> None:
    channel = reply_channel(SimpleNamespace(message_id=301))
    channel._account_id = "telegram:123"
    channel.via_account = Mock(return_value=_VIA)
    message = OutboundMessage(
        channel="telegram",
        chat_id="-1001",
        content="好",
        metadata={
            "chat_type": "supergroup",
            "external_message_id": "55",
            "mention_ids": ["902"],
        },
        committed_message_id="committed",
    )

    await channel._on_response(message)

    sent = channel._app.bot.send_message.await_args.kwargs
    assert sent["reply_parameters"].message_id == 55
    assert sent["text"].startswith("@902 ")
    assert sent["entities"][0]["url"] == "tg://user?id=902"
    channel._channel_hub.mark_delivery.assert_called_once_with(
        message,
        default_channel="telegram",
        delivery_status="sent",
        external_message_id="301",
        via_account=_VIA,
    )


async def test_private_reply_neither_quotes_nor_mentions() -> None:
    channel = reply_channel(SimpleNamespace(message_id=301))
    message = OutboundMessage(
        channel="telegram",
        chat_id="123",
        content="好",
        metadata={
            "chat_type": "private",
            "external_message_id": "55",
            "mention_ids": ["902"],
        },
    )

    await channel._on_response(message)

    sent = channel._app.bot.send_message.await_args.kwargs
    assert "reply_parameters" not in sent
    assert sent["text"] == "好"
