"""Private push drafts owned by one passive reasoning task.

Desktop pushes are held here and delivered once the turn commits; texts and
images the turn already delivered through an external channel are held here
too, so they are recorded with the turn (in its commit and
``committed_message_ids``).
A turn that never commits drops its desktop drafts (never sent) but still
records what it already delivered (``abandoned``).
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime
from typing import Any
from session.manager.models import CONTEXT_TURN_STARTED_AT

logger = logging.getLogger("agent.turns.turn_pushes")

_current: ContextVar["TurnPushDrafts | None"] = ContextVar(
    "passive_turn_pushes", default=None
)


class TurnPushDrafts:
    """Collect ordered pushes without exposing them before the turn commits."""

    def __init__(self, session_key: str, *, started_at: datetime | None = None) -> None:
        self.session_key = session_key
        self._started_at = (started_at or datetime.now().astimezone()).isoformat()
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
        message.setdefault("metadata", {})[CONTEXT_TURN_STARTED_AT] = self._started_at
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

    async def abandoned(self, *, turn_error: BaseException | None = None) -> None:
        """Records delivered drafts of a turn that never committed; once, in order.

        A no-op after ``committed``. Every record runs even if an earlier one
        fails. The failures are raised together, unless the turn itself failed
        with ``turn_error``: that error stays the one raised, and the failures
        are logged and noted on it instead of replacing it.
        """
        records, self._if_abandoned = self._if_abandoned, []
        errors: list[Exception] = []
        for record in records:
            try:
                await record()
            except Exception as exc:
                errors.append(exc)
        if not errors:
            return
        failure = ExceptionGroup("回合内已送达的推送未能记录", errors)
        if turn_error is None:
            raise failure
        # 回合自身的异常优先抛出；记录失败只随之可见，不覆盖它。
        logger.error(
            "[turn_pushes] %s 回合失败后，%d 条已送达的推送未能记录",
            self.session_key,
            len(errors),
            exc_info=failure,
        )
        turn_error.add_note(f"另有 {len(errors)} 条回合内已送达的推送未能记录")


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
