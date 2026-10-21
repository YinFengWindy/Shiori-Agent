"""Only explicit platform receipts authorize advancing an acknowledged batch."""

import pytest
import asyncio

from bus.acknowledged import deliver_acknowledged
from shiori_sdk.messages import DeliveryOutcome, OutboundMessage
from shiori_sdk.channels.errors import NonRetryableDeliveryError


@pytest.mark.parametrize(
    "reported,raises,expected",
    [
        (
            DeliveryOutcome("sent", "platform"),
            False,
            DeliveryOutcome("sent", "platform"),
        ),
        (DeliveryOutcome("failed"), True, DeliveryOutcome("failed")),
        (
            DeliveryOutcome("sent", "partial"),
            True,
            DeliveryOutcome("uncertain", "partial"),
        ),
        (None, True, DeliveryOutcome("uncertain")),
        (None, False, DeliveryOutcome("uncertain")),
        (DeliveryOutcome("sent"), False, DeliveryOutcome("uncertain")),
        (DeliveryOutcome("failed"), "cancelled", DeliveryOutcome("uncertain")),
    ],
)
async def test_callback_completion_is_not_a_platform_ack(reported, raises, expected):
    calls = []

    async def callback(message):
        calls.append(message)
        message.delivery_outcome = reported
        if raises == "cancelled":
            raise asyncio.CancelledError
        if raises:
            raise NonRetryableDeliveryError("unknown or rejected")

    message = OutboundMessage("chat", "one", "text")
    assert await deliver_acknowledged(message, (callback,)) == expected
    assert calls == [message]
