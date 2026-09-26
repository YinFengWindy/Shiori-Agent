"""Normal reply delivery records the platform receipt, never the trigger ID."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from bus.events import OutboundMessage
from plugins.qq.backend.channel.outbound import _OutboundMixin


def channel_with_receipts(text_id, image_id):
    channel = _OutboundMixin()
    channel._api = SimpleNamespace(
        send_private_text=AsyncMock(return_value=text_id),
        send_group_text=AsyncMock(return_value=text_id),
        send_private_image=AsyncMock(return_value=image_id),
        send_group_image=AsyncMock(return_value=image_id),
    )

    async def run(coro):
        return await coro

    channel._run_on_bot_loop = run
    channel._send_private_trace = AsyncMock()
    channel._channel_hub = Mock()
    channel._trace_states = {}
    return channel


@pytest.mark.parametrize("chat_id", ["123", "gqq:123"])
@pytest.mark.parametrize(
    ("content", "media", "text_id", "image_id", "expected"),
    [
        ("reply", [], 201, 202, "201"),
        ("reply", ["https://example.test/image"], 201, 202, "201"),
        ("", ["https://example.test/image"], 201, 202, "202"),
        ("", ["https://example.test/one", "https://example.test/two"], 201, 202, "202"),
        ("reply", [], None, None, ""),
    ],
)
async def test_response_records_first_send_receipt(
    chat_id, content, media, text_id, image_id, expected
):
    channel = channel_with_receipts(text_id, image_id)
    if len(media) > 1:
        channel._api.send_private_image.side_effect = [202, 299]
        channel._api.send_group_image.side_effect = [202, 299]
    message = OutboundMessage(
        channel="qq",
        chat_id=chat_id,
        content=content,
        media=media,
        metadata={"external_message_id": "incoming"},
        committed_message_id="committed",
    )
    await channel._on_response(message)
    channel._channel_hub.mark_delivery.assert_called_once_with(
        message,
        default_channel="qq",
        delivery_status="sent",
        external_message_id=expected,
    )


@pytest.mark.parametrize(
    "failure", [RuntimeError("send failed"), asyncio.CancelledError()]
)
async def test_failed_response_never_records_incoming_id_or_sent(failure):
    channel = channel_with_receipts(201, 202)
    channel._api.send_private_text.side_effect = failure
    message = OutboundMessage(
        channel="qq",
        chat_id="123",
        content="reply",
        metadata={"external_message_id": "incoming"},
    )
    with pytest.raises(type(failure)):
        await channel._on_response(message)
    channel._channel_hub.mark_delivery.assert_called_once_with(
        message, default_channel="qq", delivery_status="failed", external_message_id=""
    )
