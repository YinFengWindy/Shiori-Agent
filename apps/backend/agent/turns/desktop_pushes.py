"""Private push drafts owned by one passive reasoning task.

Desktop pushes are held here and delivered once the turn commits; texts the
turn already delivered through an external channel are held here too, so
they are recorded with the turn (in its commit and ``committed_message_ids``).
"""

import asyncio
from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

_current: ContextVar["DesktopPushDrafts | None"] = ContextVar(
    "passive_desktop_pushes", default=None
)


class DesktopPushDrafts:
    """Collect ordered pushes without exposing them before the turn commits."""

    def __init__(self, session_key: str) -> None:
        self.session_key = session_key
        self.messages: list[dict[str, Any]] = []
        self._task = asyncio.current_task()
        self._active = False
        self._effects: dict[object, Callable[[], Awaitable[None]]] = {}

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
    ) -> None:
        """Registers one draft and deduplicates its transport's commit effects.

        ``after_commit`` is the transport's effect once the turn is durable
        (e.g. delivering desktop pushes); a draft already delivered has none.
        """
        if not self._active or self._task is not asyncio.current_task():
            raise RuntimeError("桌面推送回合已结束")
        self.messages.append(message)
        if after_commit is not None:
            self._effects[owner] = after_commit

    async def committed(self) -> None:
        """Applies transport effects once, only after durable message publication."""
        effects, self._effects = self._effects, {}
        for effect in effects.values():
            await effect()


def current_desktop_pushes(session_key: str) -> DesktopPushDrafts | None:
    """Matches a desktop target to its live host turn, excluding detached tasks."""
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
