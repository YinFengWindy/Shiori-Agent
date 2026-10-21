"""Generation-owned channel reply sequence lifetime and transport context."""

from __future__ import annotations

import asyncio
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass

from bus.queue import MessageBus


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
        self._stopped = True
        for task in tuple(self._tasks):
            task.cancel()

    def resume(self) -> None:
        """Restore admission after an unsuccessful runtime replacement."""
        self._stopped = False
