"""One-attempt outbound acknowledgements, owned by the bus channel lane."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

from shiori_sdk.messages import DeliveryOutcome, OutboundMessage

logger = logging.getLogger(__name__)


async def deliver_acknowledged(
    message: OutboundMessage,
    callbacks: tuple[Callable[[OutboundMessage], Awaitable[None]], ...],
) -> DeliveryOutcome:
    """Run the sole transport once; never infer delivery from callback return.

    A missing or ambiguous transport has not started a platform request. Once
    started, any exception or missing receipt is uncertain and is never retried.
    The caller owns the transport lock and waits for this callback to finish.
    """
    if len(callbacks) != 1:
        return DeliveryOutcome("failed")
    try:
        await callbacks[0](message)
    except (Exception, asyncio.CancelledError) as error:
        logger.exception("Acknowledged delivery failed for %s", message.channel)
        receipt = message.delivery_outcome
        if (
            receipt is not None
            and receipt.status == "failed"
            and not receipt.external_message_id
            and not isinstance(error, asyncio.CancelledError)
        ):
            return receipt
        return DeliveryOutcome(
            "uncertain", receipt.external_message_id if receipt is not None else ""
        )
    receipt = message.delivery_outcome
    if (
        receipt is not None
        and receipt.status == "failed"
        and not receipt.external_message_id
    ):
        return receipt
    if receipt is None or receipt.status != "sent" or not receipt.external_message_id:
        return DeliveryOutcome(
            "uncertain", receipt.external_message_id if receipt is not None else ""
        )
    return receipt


async def finish_started[T](
    operation: Awaitable[T], *, on_cancel: Callable[[], None] | None = None
) -> T:
    """Finish one started platform operation and bookkeeping before cancellation."""
    task = asyncio.ensure_future(operation)
    cancelled = False
    while True:
        try:
            result = await asyncio.shield(task)
            break
        except asyncio.CancelledError:
            if on_cancel is not None:
                on_cancel()
            if task.cancelled():
                raise
            cancelled = True
    if cancelled:
        raise asyncio.CancelledError
    return result
