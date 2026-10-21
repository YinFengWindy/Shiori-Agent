"""Generation-owned channel reply sequence lifetime and transport context."""

from __future__ import annotations

import asyncio
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass

from bus.queue import MessageBus
from agent.turns.reply_interruption import ReplyInterruption
from shiori_sdk.messages import InboundMessage
from shiori_sdk.channels.chat_types import is_group_chat_type


def channel_reply_scope(message: InboundMessage) -> tuple[str, ...]:
    """Exact receiving chat, independent of its shared role session and speaker."""
    metadata = message.metadata
    return (
        str(metadata.get("role_id") or message.session_key),
        message.channel,
        str(metadata.get("account_id") or ""),
        "group" if is_group_chat_type(metadata.get("chat_type")) else "private",
        message.chat_id,
        str(metadata.get("message_thread_id") or ""),
    )


@dataclass(frozen=True)
class ChannelSequenceContext:
    """Accepted ordinary channel turn, bound by its runtime dispatcher."""

    owner: ChannelSequenceOwner
    bus: MessageBus


_CURRENT: ContextVar[ChannelSequenceContext | None] = ContextVar(
    "channel_reply_sequence", default=None
)


def channel_sequence_context() -> ChannelSequenceContext | None:
    """Return the ordinary channel delivery context, absent for direct/internal work."""
    return _CURRENT.get()


def supports_channel_sequence(channel: str) -> bool:
    """Only admitted ordinary replies with an opted-in transport can use a batch."""
    context = _CURRENT.get()
    return context is not None and context.bus.supports_reply_sequence(channel)


@contextmanager
def without_channel_sequence():
    """Direct/internal child turns do not inherit an ordinary reply's transport."""
    token = _CURRENT.set(None)
    try:
        yield
    finally:
        _CURRENT.reset(token)


class ChannelSequenceOwner:
    """Cancels pending suffixes before their runtime's channels are replaced."""

    def __init__(self) -> None:
        self._tasks: set[asyncio.Task] = set()
        self._stopped = False
        self._replies: dict[tuple[str, ...], ReplyInterruption] = {}
        self._plans: set[ReplyInterruption] = set()

    def admit(self, message: InboundMessage) -> ReplyInterruption:
        """Invalidate the same real sender's plan at accepted queue admission.

        Queued requests retain their own token and still commit their input;
        repeated supplements cannot cancel a new task through a stale lookup.
        Other group members retain the dispatcher's chat order.
        """
        key = (*channel_reply_scope(message), message.sender)
        previous = self._replies.get(key)
        if previous is not None:
            previous.invalidate()
        reply = ReplyInterruption(invalidated=self._stopped)
        self._replies[key] = reply
        self._plans.add(reply)
        return reply

    def forget(self, message: InboundMessage, reply: ReplyInterruption) -> None:
        """Release only this exact registration; an older turn owns no successor."""
        key = (*channel_reply_scope(message), message.sender)
        if self._replies.get(key) is reply:
            self._replies.pop(key)
        self._plans.discard(reply)

    @contextmanager
    def track(self, reply: ReplyInterruption | None):
        """Retain desktop natural sequences; ordinary reload behavior is unchanged."""
        if reply is not None and reply.natural_chat:
            if self._stopped:
                reply.invalidate()
            self._plans.add(reply)
        try:
            yield
        finally:
            if reply is not None:
                self._plans.discard(reply)

    @contextmanager
    def bind(self, bus: MessageBus):
        """Make this accepted runtime available to its ordinary channel turn."""
        token = _CURRENT.set(ChannelSequenceContext(self, bus))
        try:
            yield
        finally:
            _CURRENT.reset(token)

    @contextmanager
    def delivering(self):
        """Register the cancellable batch, never the shielded per-message task."""
        if self._stopped:
            raise asyncio.CancelledError
        task = asyncio.current_task()
        assert task is not None
        self._tasks.add(task)
        try:
            yield
        finally:
            self._tasks.discard(task)

    def stop(self) -> None:
        """Refuse old-runtime batches and cancel the unstarted suffix of active ones."""
        if self._stopped:
            return
        self._stopped = True
        for reply in tuple(self._plans):
            reply.invalidate()
        self._replies.clear()
        self._plans.clear()
        for task in tuple(self._tasks):
            task.cancel()

    def resume(self) -> None:
        """Restore admission after an unsuccessful runtime replacement."""
        self._stopped = False
