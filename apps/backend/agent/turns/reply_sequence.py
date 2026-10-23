"""Model-authored message lists and cancellable complete-message delivery."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any

from core.common.cancellation import finish_started
from agent.turns.reply_interruption import reply_was_invalidated
from core.roles.turn_gate import wait_outside_role_gate

_BUFFERED_REPLY: ContextVar[bool] = ContextVar("buffered_reply", default=False)


@contextmanager
def buffered_reply_scope(enabled: bool) -> Iterator[None]:
    """Keep unshown model text out of interruption snapshots for this turn."""
    token = _BUFFERED_REPLY.set(enabled)
    try:
        yield
    finally:
        _BUFFERED_REPLY.reset(token)


def reply_is_buffered() -> bool:
    """Whether progress observers must keep model text private."""
    return _BUFFERED_REPLY.get()


def presented_tool_chain(
    groups: Sequence[Mapping[str, Any]], *, buffered: bool
) -> list[dict[str, Any]]:
    """Retain tool facts and thinking while hiding dialogue never published.

    Both interrupted progress and completed results use this projection. The
    reasoning loop's private trace remains intact for subsequent model requests.
    """
    return [{**group, "text": ""} if buffered else dict(group) for group in groups]


@dataclass(frozen=True)
class ReplySequence:
    """Validated message contents in the exact order chosen by the model."""

    messages: tuple[str, ...]

    @property
    def content(self) -> str:
        """Plain dialogue used by whole-turn observers without protocol markers."""
        return "\n\n".join(self.messages)


def message_pause(content: str) -> float:
    """A short bounded reading pause; it never changes message boundaries."""
    return min(1.8, max(0.6, len(content) * 0.025))


async def wait_between_messages(seconds: float) -> None:
    """Yield during pacing; the owning seam allows tests to control time."""
    await asyncio.sleep(seconds)


def role_state_is_current(
    metadata: Mapping[str, Any], state_kwargs: Mapping[str, Any]
) -> bool:
    """A finished batch may publish mood only when no newer turn already did."""
    expected = state_kwargs.get("expected_mood_updated_at")
    turn_stamp = str(
        (state_kwargs.get("metadata_updates") or {}).get("last_turn_ts", "")
    )
    newer_turn = bool(turn_stamp) and str(metadata.get("last_turn_ts", "")) > turn_stamp
    if newer_turn:
        return False
    if expected is None:
        return True
    return str(metadata.get("current_mood_updated_at", "")) == expected


async def publish_final_role_state(
    manager: Any, session_key: str, state_kwargs: Mapping[str, Any]
) -> None:
    """Write whole-reply role state once, after the last message is durable."""
    current = manager.get_or_create(session_key)
    if role_state_is_current(current.metadata, state_kwargs):
        await manager.append_messages(current, [], **state_kwargs)


async def deliver_sequence(
    messages: Sequence[str],
    send_one: Callable[[int, str], Awaitable[None]],
    on_last: Callable[[], Awaitable[None]] | None,
    *,
    on_cancel: Callable[[], None] | None = None,
) -> None:
    """Commit and deliver each message; publish role state only after the last.

    Pacing yields the role gate. A started send finishes before cancellation
    starts the next message or abandons its receipt.
    """
    last = len(messages) - 1
    for index, content in enumerate(messages):
        if index:
            previous = messages[index - 1]
            await wait_outside_role_gate(
                lambda previous=previous: wait_between_messages(message_pause(previous))
            )
        if reply_was_invalidated():
            raise asyncio.CancelledError

        async def step(index: int = index, content: str = content) -> None:
            await send_one(index, content)
            if index == last and on_last is not None:
                await on_last()

        await finish_started(step(), on_cancel=on_cancel)


async def deliver_reply_sequence(
    sequence: ReplySequence,
    publish: Callable[[int, str], Awaitable[None]],
) -> None:
    """Publish serially; finish a started commit/event before propagating cancel."""
    await deliver_sequence(sequence.messages, publish, None)
