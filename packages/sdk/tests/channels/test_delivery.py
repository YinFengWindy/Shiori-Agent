"""A channel-owned deadline bounds one acknowledgement and exposes uncertainty."""

import asyncio

import pytest

from shiori_sdk.channels.delivery import bounded_reply_delivery, in_acknowledged_reply
from shiori_sdk.messages import DeliveryOutcome, OutboundMessage


async def test_deadline_retains_receipt_and_never_retries():
    message = OutboundMessage(
        "test", "one", "hello", metadata={"reply_sequence_id": "batch"}
    )
    calls = []

    async def send(msg):
        assert in_acknowledged_reply()
        calls.append(msg)
        msg.delivery_outcome = DeliveryOutcome("sent", "first-chunk")
        await asyncio.Event().wait()

    with pytest.raises(TimeoutError):
        await bounded_reply_delivery(message, send, timeout_seconds=0.01)
    assert calls == [message]
    assert message.delivery_outcome == DeliveryOutcome("uncertain", "first-chunk")
    assert not in_acknowledged_reply()
