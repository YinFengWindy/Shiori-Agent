"""Commit and publish each desktop reply message without exposing its suffix."""

from __future__ import annotations

from typing import Any
from collections.abc import Awaitable, Callable

from agent.turns.reply_sequence import ReplySequence, deliver_reply_sequence
from bus.event_bus import EventBus
from bus.events_lifecycle import ReplyMessageCommitted
from session.manager import Session, SessionManager


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

    await deliver_reply_sequence(sequence, publish)
