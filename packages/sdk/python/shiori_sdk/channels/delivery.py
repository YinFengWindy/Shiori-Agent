"""Bound the lifetime of one acknowledged ordinary channel reply."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from contextvars import ContextVar

from shiori_sdk.messages import DeliveryOutcome, OutboundMessage

_ACKNOWLEDGED_REPLY: ContextVar[bool] = ContextVar("acknowledged_reply", default=False)


def in_acknowledged_reply() -> bool:
    """Whether fallback/retry decisions must preserve an unknown platform outcome."""
    return _ACKNOWLEDGED_REPLY.get()


def reply_failure_status(
    message: OutboundMessage, *, rejected: bool, external_message_id: str | None = None
) -> str:
    """Distinguish a proven rejection from unknown or partially accepted sends."""
    if not message.metadata.get("reply_sequence_id") or (
        rejected and not external_message_id
    ):
        return "failed"
    return "uncertain"


async def bounded_reply_delivery(
    message: OutboundMessage,
    send: Callable[[OutboundMessage], Awaitable[None]],
    *,
    timeout_seconds: float,
) -> None:
    """Apply the channel's deadline to a natural reply including its bookkeeping.

    Legacy single-message sends retain their own transport policy. A timeout
    cannot prove rejection by the platform, so its outcome is always uncertain.
    """
    if not message.metadata.get("reply_sequence_id"):
        await send(message)
        return
    token = _ACKNOWLEDGED_REPLY.set(True)
    try:
        async with asyncio.timeout(timeout_seconds):
            await send(message)
    except TimeoutError:
        previous = message.delivery_outcome
        message.delivery_outcome = DeliveryOutcome(
            "uncertain", previous.external_message_id if previous is not None else ""
        )
        raise
    finally:
        _ACKNOWLEDGED_REPLY.reset(token)
