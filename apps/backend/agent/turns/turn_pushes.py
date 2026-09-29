"""Private push drafts owned by one passive reasoning task.

Desktop pushes are held here and delivered once the turn commits; texts the
turn already delivered through an external channel are held here too, so
they are recorded with the turn (in its commit and ``committed_message_ids``).
A turn that never commits drops its desktop drafts (never sent) but still
records what it already delivered (``abandoned``).
"""

import asyncio
from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

_current: ContextVar["TurnPushDrafts | None"] = ContextVar(
    "passive_turn_pushes", default=None
)


class TurnPushDrafts:
    """Collect ordered pushes without exposing them before the turn commits."""

    def __init__(self, session_key: str) -> None:
        self.session_key = session_key
        self.messages: list[dict[str, Any]] = []
        self._task = asyncio.current_task()
        self._active = False
        self._effects: dict[object, Callable[[], Awaitable[None]]] = {}
        self._if_abandoned: list[Callable[[], Awaitable[None]]] = []

    @contextmanager
    def collect(self) -> Iterator[None]:
        """Admits drafts only while the owning task is reasoning."""
        token = _current.set(self)
        self._active = True
        try:
            yield
        finally:
            self._active = False
            _current.reset(token)

    def append(
        self,
        message: dict[str, Any],
        *,
        owner: object,
        after_commit: Callable[[], Awaitable[None]] | None = None,
        if_abandoned: Callable[[], Awaitable[None]] | None = None,
    ) -> None:
        """Registers one draft and deduplicates its transport's commit effects.

        ``after_commit`` is the transport's effect once the turn is durable
        (e.g. delivering desktop pushes); a draft already delivered has none
        but an ``if_abandoned`` record of the delivery, run if the turn never
        commits.
        """
        if not self._active or self._task is not asyncio.current_task():
            raise RuntimeError("推送所属回合已结束")
        self.messages.append(message)
        if after_commit is not None:
            self._effects[owner] = after_commit
        if if_abandoned is not None:
            self._if_abandoned.append(if_abandoned)

    async def committed(self) -> None:
        """Applies transport effects once, only after durable message publication."""
        self._if_abandoned = []
        effects, self._effects = self._effects, {}
        for effect in effects.values():
            await effect()

    async def abandoned(self) -> None:
        """Records delivered drafts of a turn that never committed; once, in order.

        A no-op after ``committed``.
        """
        records, self._if_abandoned = self._if_abandoned, []
        for record in records:
            await record()


def current_turn_pushes(session_key: str) -> TurnPushDrafts | None:
    """The live host turn of ``session_key`` in this task, if any (never a detached task)."""
    current = _current.get()
    if (
        current is not None
        and current._active
        and current._task is asyncio.current_task()
        and session_key.startswith("role:")
        and current.session_key == session_key
    ):
        return current
    return None
