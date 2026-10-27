"""Invalidate private reply plans without cancelling an executing tool."""

from __future__ import annotations

import asyncio
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from collections.abc import Callable
from typing import TYPE_CHECKING

from core.roles.natural_chat import natural_chat_enabled

if TYPE_CHECKING:
    from core.roles.store import RoleRecord


class ReplyPlanInvalidated(RuntimeError):
    """A private plan reached another provider boundary after being superseded."""


@dataclass(eq=False)
class ReplyInterruption:
    """One accepted reply's lifetime, from generation through its final delivery.

    During generation invalidation is cooperative: the completed tool trace is
    committed before the reply is discarded. Only the delivery phase permits
    task cancellation, where each started send/commit already has protection.
    """

    invalidated: bool = False
    natural_chat: bool = True
    visible_reply: str = ""
    visible_thinking: str = ""
    role_lookup: Callable[[], RoleRecord | None] | None = None
    _delivery: asyncio.Task | None = field(default=None, init=False)

    def invalidate(self) -> None:
        """Stop this plan once; repeated input must not cancel its cleanup."""
        if self.invalidated:
            return
        self.invalidated = True
        if self._delivery is not None and self._delivery is not asyncio.current_task():
            self._delivery.cancel()

    def refresh(self) -> bool:
        """Stop at the next safe boundary after role removal or capability disable."""
        if self.role_lookup is not None:
            role = self.role_lookup()
            if role is None:
                # The deletion owner has removed its session too. No completion
                # may recreate that session or publish the removed role's tail.
                raise asyncio.CancelledError
            if self.natural_chat and not natural_chat_enabled(role):
                self.invalidate()
        return self.invalidated

    def record_visible_delta(self, content: str, thinking: str) -> None:
        """Freeze ordinary desktop text at the last started stream publication."""
        if not self.invalidated:
            self.visible_reply += content
            self.visible_thinking += thinking

    @contextmanager
    def delivering(self):
        """Permit immediate cancellation only around protected delivery work."""
        if self.refresh():
            raise asyncio.CancelledError
        self._delivery = asyncio.current_task()
        try:
            yield
        finally:
            self._delivery = None


_CURRENT: ContextVar[ReplyInterruption | None] = ContextVar(
    "reply_interruption", default=None
)


@contextmanager
def reply_interruption_scope(interruption: ReplyInterruption | None):
    """Bind the exact accepted plan, never a mutable session-wide lookup."""
    token = _CURRENT.set(interruption)
    try:
        yield
    finally:
        _CURRENT.reset(token)


def current_reply_interruption() -> ReplyInterruption | None:
    """Return the desktop, admitted channel or owned natural report plan.

    Other internal/direct turns have no interruption context.
    """
    return _CURRENT.get()


def reply_was_invalidated() -> bool:
    """Whether a new admitted input superseded this unsent reply."""
    current = _CURRENT.get()
    return current is not None and current.refresh()


@contextmanager
def interruptible_reply_delivery():
    """Enable suffix cancellation without changing ordinary reply behavior."""
    current = _CURRENT.get()
    if current is None:
        yield
    else:
        with current.delivering():
            yield
