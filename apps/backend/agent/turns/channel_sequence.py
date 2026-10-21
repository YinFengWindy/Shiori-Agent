"""Generation-owned channel reply sequence lifetime and transport context."""

from __future__ import annotations

import asyncio
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from collections.abc import Iterator

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
    """A runtime's reply transport, shared by admitted turns and owned reports."""

    owner: ChannelSequenceOwner
    bus: MessageBus


@dataclass(eq=False)
class BackgroundReply:
    """One role report's exact destination, optional addressees and lifetime."""

    origin: InboundMessage
    interruption: ReplyInterruption
    task: asyncio.Task
    senders: frozenset[str] | None


_CURRENT: ContextVar[ChannelSequenceContext | None] = ContextVar(
    "channel_reply_sequence", default=None
)


def channel_sequence_context() -> ChannelSequenceContext | None:
    """Return the bound transport; unintegrated direct/internal work has none."""
    return _CURRENT.get()


def supports_channel_sequence(channel: str) -> bool:
    """A batch needs both a runtime owner and an opted-in channel transport."""
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
        self._stopped = False
        self._replies: dict[tuple[str, ...], ReplyInterruption] = {}
        self._plans: set[ReplyInterruption] = set()
        self._background: set[BackgroundReply] = set()

    def admit(self, message: InboundMessage) -> ReplyInterruption:
        """Invalidate the same real sender's plan at accepted queue admission.

        Queued requests retain their own token and still commit their input;
        repeated supplements cannot cancel a new task through a stale lookup.
        Other group members retain the dispatcher's chat order.
        """
        key = (*channel_reply_scope(message), message.sender)
        self.interrupt_background(message)
        previous = self._replies.get(key)
        if previous is not None:
            previous.invalidate()
        reply = ReplyInterruption(invalidated=self._stopped)
        self._replies[key] = reply
        self._plans.add(reply)
        return reply

    def interrupt_background(self, message: InboundMessage) -> None:
        """Invalidate matching role output only after real input was admitted."""
        scope = channel_reply_scope(message)
        for reply in tuple(self._background):
            if channel_reply_scope(reply.origin) != scope:
                continue
            if reply.senders is None or message.sender in reply.senders:
                reply.interruption.invalidate()

    def background_tasks(self, message: InboundMessage) -> tuple[asyncio.Task, ...]:
        """Keep accepted requests behind an earlier report in this exact chat."""
        scope = channel_reply_scope(message)
        return tuple(
            reply.task
            for reply in self._background
            if channel_reply_scope(reply.origin) == scope
            and reply.task is not asyncio.current_task()
        )

    def owns_background(self, interruption: ReplyInterruption | None) -> bool:
        """Only a registered report may opt an internal turn into natural delivery."""
        return any(reply.interruption is interruption for reply in self._background)

    @contextmanager
    def background_reply(
        self,
        origin: InboundMessage,
        interruption: ReplyInterruption,
        *,
        senders: frozenset[str] | None,
    ) -> Iterator[BackgroundReply]:
        """Register generation-owned output without admitting a synthetic user."""
        task = asyncio.current_task()
        assert task is not None
        reply = self.register_background(origin, interruption, task, senders=senders)
        try:
            yield reply
        finally:
            self.forget_background(reply)

    def register_background(
        self,
        origin: InboundMessage,
        interruption: ReplyInterruption,
        task: asyncio.Task,
        *,
        senders: frozenset[str] | None,
    ) -> BackgroundReply:
        """Register a queued report synchronously before another input can arrive."""
        reply = BackgroundReply(origin, interruption, task, senders)
        if self._stopped:
            interruption.invalidate()
        self._background.add(reply)
        self._plans.add(interruption)
        return reply

    def forget_background(self, reply: BackgroundReply) -> None:
        """Retire this report's registration without touching a successor."""
        self._background.discard(reply)
        self._plans.discard(reply.interruption)

    def retarget_background(
        self,
        reply: BackgroundReply,
        origin: InboundMessage,
        *,
        senders: frozenset[str] | None,
    ) -> None:
        """Move a draft to a validated destination without overlooking queued input."""
        reply.origin = origin
        reply.senders = senders
        scope = channel_reply_scope(origin)
        if any(
            key[:-1] == scope and (senders is None or key[-1] in senders)
            for key in self._replies
        ):
            reply.interruption.invalidate()

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

    def stop(self) -> None:
        """Refuse old-runtime batches and invalidate their unstarted suffixes."""
        if self._stopped:
            return
        self._stopped = True
        for reply in tuple(self._plans):
            reply.invalidate()
        self._replies.clear()
        self._plans.clear()

    def resume(self) -> None:
        """Restore admission after an unsuccessful runtime replacement."""
        self._stopped = False
