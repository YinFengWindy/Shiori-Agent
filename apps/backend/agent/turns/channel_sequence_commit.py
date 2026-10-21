"""Commit and deliver only the current ordinary channel reply segment."""

from __future__ import annotations

import asyncio

from collections.abc import Awaitable, Callable
from typing import Any

from agent.turns.channel_sequence import channel_sequence_context
from agent.turns.reply_interruption import interruptible_reply_delivery
from agent.turns.reply_sequence import (
    ReplySequence,
    deliver_sequence,
    publish_final_role_state,
)
from agent.turns.outbound import sanitize_user_visible_content
from session.manager import Session, SessionManager
from session.manager.models import build_session_message
from shiori_sdk.messages import OutboundMessage
from shiori_sdk.channels.chat_types import REPLY_MENTION_IDS_KEY


class ChannelSequenceDeliveryError(RuntimeError):
    """A batch stopped after a failed or uncertain current segment."""


async def commit_channel_reply_sequence(
    *,
    manager: SessionManager,
    session: Session,
    messages: list[dict[str, Any]],
    sequence: ReplySequence,
    state_kwargs: dict[str, Any],
    metadata: dict[str, Any],
    channel: str,
    chat_id: str,
    extra_media: list[str],
    on_first_commit: Callable[[], Awaitable[None]] | None = None,
) -> None:
    """Persist one pending row, await the channel receipt, then advance.

    The private suffix is never queued or stored. Pending/uncertain rows are
    delivery records, excluded from shared model/memory history. A completed
    older batch may append facts but cannot overwrite a newer reply's state.
    """
    context = channel_sequence_context()
    if context is None:
        raise RuntimeError("Channel reply sequence requires an admitted transport")
    prefix = messages[: -len(sequence.messages)]
    replies = messages[-len(sequence.messages) :]
    if replies[0].get("tool_chain"):
        # Executed tools are facts even if the first spoken message is uncertain.
        # Keep their trace outside the delivery row so history never replays a
        # tool merely because the corresponding natural-language send failed.
        first = replies[0]
        trace_metadata = dict(first["metadata"])
        trace_metadata.pop("reply_sequence_id", None)
        trace_metadata.pop("reply_sequence_index", None)
        for key in ("mood", "thought"):
            trace_metadata.pop(key, None)
        trace = build_session_message(
            "assistant",
            "",
            metadata=trace_metadata,
            thread_id=first.get("thread_id"),
            tool_chain=first.pop("tool_chain"),
            tools_used=first.pop("tools_used", None),
        )
        prefix.append(trace)
        messages.insert(len(prefix) - 1, trace)
    current_message: OutboundMessage | None = None
    cancelled = False

    def cancel_pending() -> None:
        nonlocal cancelled
        cancelled = True
        if current_message is not None:
            context.bus.cancel_waiting_outbound(current_message)

    async def publish(index: int, _content: str) -> None:
        nonlocal current_message
        if cancelled:
            raise asyncio.CancelledError
        reply = replies[index]
        if index == 0:
            await manager.append_messages(session, prefix, pending_messages=True)
            if on_first_commit is not None:
                await on_first_commit()
        trigger = next(
            (str(item["id"]) for item in prefix if item["role"] == "user"), ""
        )
        reply["metadata"]["trigger_user_message_id"] = trigger
        reply["delivery_status"] = "pending"
        await manager.append_messages(session, [reply], pending_messages=True)
        outgoing = {**metadata, **reply["metadata"], "streamed_reply": False}
        # The transport still needs the incoming platform id for quoting.
        outgoing["external_message_id"] = metadata.get("external_message_id", "")
        if index:
            outgoing.pop(REPLY_MENTION_IDS_KEY, None)
        message = OutboundMessage(
            channel=channel,
            chat_id=chat_id,
            content=sanitize_user_visible_content(reply["content"]),
            thinking=reply.get("reasoning_content"),
            media=list(
                dict.fromkeys(
                    [*(reply.get("media") or []), *(extra_media if index == 0 else [])]
                )
            ),
            metadata=outgoing,
            committed_message_id=str(reply["id"]),
        )
        current_message = message
        try:
            if cancelled:
                raise asyncio.CancelledError
            receipt = await context.bus.deliver_outbound(message)
        except asyncio.CancelledError:
            manager.mark_message_delivery(
                session.key,
                message_id=str(reply["id"]),
                thread_id=str(outgoing["thread_id"]),
                delivery_status="failed",
            )
            raise
        manager.mark_message_delivery(
            session.key,
            message_id=str(reply["id"]),
            thread_id=str(outgoing["thread_id"]),
            delivery_status=receipt.status,
            external_message_id=receipt.external_message_id,
        )
        if receipt.status != "sent":
            raise ChannelSequenceDeliveryError(
                f"{channel} reply delivery {receipt.status}"
            )

    async def on_last() -> None:
        # A different chat may have completed while this batch was pacing.
        # Its newer whole-turn state wins; this batch's facts already exist
        # on their own messages, including tools and usage.
        await publish_final_role_state(manager, session.key, state_kwargs)

    with interruptible_reply_delivery():
        await deliver_sequence(
            sequence.messages, publish, on_last, on_cancel=cancel_pending
        )
