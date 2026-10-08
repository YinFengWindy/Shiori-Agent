"""Per-turn state of a renderer-owned desktop chat turn and its terminal guarantee."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, TypeVar

from agent.looping.interrupt import TurnInterruptState

T = TypeVar("T")

EventEmitter = Callable[[dict[str, Any]], Awaitable[None] | None]

#: Every started desktop turn ends with exactly one of these bridge events.
TERMINAL_CHAT_METHODS = frozenset({"chat.done", "chat.error", "chat.cancelled"})

#: Events held back until the turn has released its session, so that a
#: renderer receiving them may immediately send the next turn.
DEFERRED_CHAT_METHODS = TERMINAL_CHAT_METHODS | {"session.updated"}


@dataclass(eq=False)
class DesktopChatTurn:
    """Tracks one renderer-owned turn without sharing state across sessions."""

    request_id: str
    turn_id: str
    session_key: str
    emit_event: EventEmitter
    task: asyncio.Task[None] = field(init=False)
    #: The session is released; the turn may still be publishing its terminal.
    completed: bool = False
    #: The terminal has been claimed by exactly one finisher.
    finished: bool = False
    #: Publishes the terminal of a turn cancelled before its first step.
    late_finisher: asyncio.Task[None] | None = None
    #: Snapshot taken by an accepted turn-id cancel, persisted by the finisher.
    interrupt_state: TurnInterruptState | None = None
    interrupted_message: dict[str, Any] | None = None
    #: Deferred terminal and session events, published together at the end.
    deferred_events: list[dict[str, Any]] = field(default_factory=list)

    def has_terminal(self) -> bool:
        """Returns whether chat.done / chat.error / chat.cancelled is already queued."""

        return any(
            event.get("method") in TERMINAL_CHAT_METHODS
            for event in self.deferred_events
        )


async def complete_despite_cancellation(operation: Awaitable[T]) -> T:
    """Runs ``operation`` to completion even if the awaiting task is cancelled.

    Used for the terminal flush and interrupted-reply persistence: a bridge
    shutdown cancelling a turn mid-publication must not drop half of its
    terminal events. The caller's cancellation is absorbed, as the turn runner
    already ends quietly on cancellation.
    """

    inner = asyncio.ensure_future(operation)
    while True:
        try:
            return await asyncio.shield(inner)
        except asyncio.CancelledError:
            if inner.done():
                return inner.result()
