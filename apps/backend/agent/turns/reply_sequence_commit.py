"""Commit and publish each desktop reply message without exposing its suffix."""

from __future__ import annotations

import asyncio
from typing import Any
from collections.abc import Awaitable, Callable

from agent.turns.reply_sequence import ReplySequence, deliver_reply_sequence
from bus.event_bus import EventBus
from bus.events_lifecycle import ReplyMessageCommitted
from session.manager import Session, SessionManager
from core.common.cancellation import finish_started
from agent.turns.reply_interruption import (
    interruptible_reply_delivery,
    current_reply_interruption,
)
from agent.turns.reply_sequence import presented_tool_chain


async def commit_invalidated_reply(
    *,
    manager: SessionManager,
    bus: EventBus,
    session: Session,
    messages: list[dict[str, Any]],
    sequence: ReplySequence,
    desktop: bool,
    on_first_commit: Callable[[], Awaitable[None]] | None = None,
) -> None:
    """Keep accepted input, executed tools and a published desktop prefix.

    This is the generation/tool completion boundary. It does not run the usual
    reply/mood/memory effects, saves no unseen suffix and never retries the old plan.
    """
    prefix = messages[: -len(sequence.messages)]
    first = messages[-len(sequence.messages)]
    interruption = current_reply_interruption()
    ordinary = interruption is not None and not interruption.natural_chat
    content = interruption.visible_reply if ordinary else ""
    thinking = (
        interruption.visible_thinking if ordinary else first.get("reasoning_content")
    )
    if content or first.get("tool_chain") or thinking:
        metadata = {**first["metadata"], "interrupted_reply": True}
        for key in ("reply_sequence_id", "reply_sequence_index", "mood", "thought"):
            metadata.pop(key, None)
        # The visible ordinary prefix already includes tool preambles. Keep
        # their completed calls without duplicating text or saving later output.
        chain = presented_tool_chain(first.get("tool_chain") or [], buffered=True)
        if ordinary:
            chain = [{**group, "reasoning_content": ""} for group in chain]
        metadata["tool_chain"] = chain
        trace = {
            **first,
            "content": content,
            "reasoning_content": thinking,
            "tool_chain": chain,
            "metadata": metadata,
        }
        trace.pop("media", None)
        prefix.append(trace)

    async def commit() -> None:
        await manager.append_messages(session, prefix, pending_messages=True)
        if on_first_commit is not None:
            await on_first_commit()
        if desktop and prefix:
            await bus.emit(
                ReplyMessageCommitted(
                    session_key=session.key,
                    turn_id=str(first["metadata"]["turn_id"]),
                    message_ids=tuple(str(message["id"]) for message in prefix),
                )
            )

    await finish_started(commit())
    raise asyncio.CancelledError


async def commit_reply_sequence(
    *,
    manager: SessionManager,
    bus: EventBus,
    session: Session,
    messages: list[dict[str, Any]],
    sequence: ReplySequence,
    state_kwargs: dict[str, Any],
    on_first_commit: Callable[[], Awaitable[None]] | None = None,
) -> None:
    """Store each actual message before publishing it; never commit pending text.

    The earlier user/tool drafts travel with the first message. Mood and other
    whole-reply state travel with the last, so a cancelled prefix cannot publish
    state derived from words that were never sent.
    """
    prefix = messages[: -len(sequence.messages)]
    replies = messages[-len(sequence.messages) :]

    async def publish(index: int, _content: str) -> None:
        reply = replies[index]
        batch = [*prefix, reply] if index == 0 else [reply]
        final = index == len(replies) - 1
        kwargs = (
            state_kwargs
            if final
            else {
                "pending_messages": True,
                "expected_mood_updated_at": state_kwargs.get(
                    "expected_mood_updated_at"
                ),
            }
        )
        await manager.append_messages(session, batch, **kwargs)
        if index == 0 and on_first_commit is not None:
            await on_first_commit()
        # emit is a required publication boundary, not a best-effort observer.
        await bus.emit(
            ReplyMessageCommitted(
                session_key=session.key,
                turn_id=str(reply["metadata"]["turn_id"]),
                message_ids=tuple(str(message["id"]) for message in batch),
            )
        )

    with interruptible_reply_delivery():
        await deliver_reply_sequence(sequence, publish)
