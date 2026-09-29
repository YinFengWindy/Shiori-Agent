"""Validate and commit prepared memory consolidation under session ownership."""

import asyncio
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from session.store.common import CONTEXT_CURSORS_METADATA_KEY, ContextScope

from .manager import _ManagerCoreMixin
from .models import stored_context_cursors


@dataclass(frozen=True)
class ConsolidationCommitRequest:
    """Message prefix and cursor observed before preparing memory side effects.

    两种游标二选一：只有一段对话的会话给出 ``expected_last_consolidated`` 与
    ``last_consolidated``；角色会话给出按上下文的 ``expected_context_cursors`` 与
    ``context_cursors``（键相同，只含本次推进的上下文），只校验并推进这些上下文的
    游标，其余上下文的游标不变，``last_consolidated`` 随之取各游标的最小值（#523）。
    """

    session_key: str
    expected_message_ids: tuple[str, ...]
    expected_last_consolidated: int | None = None
    last_consolidated: int | None = None
    expected_context_cursors: Mapping[ContextScope, int] = field(default_factory=dict)
    context_cursors: Mapping[ContextScope, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        single = (self.expected_last_consolidated, self.last_consolidated)
        if set(self.expected_context_cursors) != set(self.context_cursors):
            raise ValueError("按上下文的预期游标与新游标必须对应同一组上下文")
        if self.context_cursors:
            if single != (None, None):
                raise ValueError("整理提交不能同时给出会话游标与按上下文的游标")
        elif None in single:
            raise ValueError("整理提交缺少会话游标")


class _ConsolidationMixin(_ManagerCoreMixin):
    async def commit_consolidation(
        self,
        request: ConsolidationCommitRequest,
        write_memory: Callable[[], Awaitable[None]],
        publish_committed: Callable[[], Awaitable[None]] | None = None,
    ) -> bool:
        """Commit a still-current draft and its cursor, serialized with undo.

        A changed prefix or cursor returns False before any memory side effect.
        New messages appended after the prepared prefix do not invalidate it.
        Write durable Markdown first, then persist the cursor and publish awaited
        memory consumers, all under one lock. A publishing failure preserves the
        already committed cursor and propagates to the caller. Neither callback
        may reacquire the session lock through save_async.
        Cancellation after commit starts is deferred until every started write and
        consumer settles, so a to_thread writer cannot outlive this lock.
        """
        targets = (
            list(request.context_cursors.values())
            if request.context_cursors
            else [request.last_consolidated]
        )
        if not all(
            target is not None and 0 <= target <= len(request.expected_message_ids)
            for target in targets
        ):
            raise ValueError("整理游标超出准备的消息范围")
        async with self._lock(request.session_key):
            messages = self._store.fetch_session_messages(request.session_key)
            meta = self._store.get_session_meta(request.session_key)
            expected = request.expected_message_ids
            if (
                meta is None
                or not expected
                or not all(expected)
                or tuple(str(message["id"]) for message in messages[: len(expected)])
                != expected
            ):
                return False
            next_cursors = _next_cursors(request, meta)
            if next_cursors is None:
                return False
            last_consolidated, context_cursors = next_cursors

            async def finish_commit() -> None:
                await write_memory()
                self._store.update_last_consolidated(
                    request.session_key,
                    last_consolidated,
                    context_cursors=context_cursors,
                )
                session = self._cache.get(request.session_key)
                if session is not None:
                    session.last_consolidated = last_consolidated
                    if context_cursors is not None:
                        session.metadata = {
                            **session.metadata,
                            CONTEXT_CURSORS_METADATA_KEY: context_cursors,
                        }
                    session.updated_at = datetime.now()
                if publish_committed is not None:
                    await publish_committed()

            # Cancelling an asyncio.to_thread await does not stop its underlying write.
            # Shield the whole commit and defer even repeated cancellation requests.
            pending = asyncio.gather(finish_commit(), return_exceptions=True)
            cancelled: asyncio.CancelledError | None = None
            while not pending.done():
                try:
                    await asyncio.shield(pending)
                except asyncio.CancelledError as exc:
                    cancelled = exc
            outcome = pending.result()[0]
            if cancelled is not None:
                if isinstance(outcome, BaseException):
                    raise cancelled from outcome
                raise cancelled
            if isinstance(outcome, BaseException):
                raise outcome
            return True


def _next_cursors(
    request: ConsolidationCommitRequest, meta: dict[str, Any]
) -> tuple[int, dict[ContextScope, int] | None] | None:
    """校验提交时看到的游标仍是准备时的值，返回提交后的低水位与按上下文游标。

    游标已被别的提交或撤销改动时返回 None（过时草稿，不产生任何副作用）。按上下文
    提交只比较本次推进的那些上下文，另一类上下文的游标怎么变都不影响本次提交。
    """
    stored_last = int(meta["last_consolidated"])
    metadata = meta["metadata"]
    if not request.context_cursors:
        if CONTEXT_CURSORS_METADATA_KEY in metadata:
            raise ValueError("会话已按上下文记录整理游标，必须按上下文提交")
        if (
            request.last_consolidated is None
            or stored_last != request.expected_last_consolidated
        ):
            return None
        return request.last_consolidated, None
    current = stored_context_cursors(metadata, stored_last)
    if any(
        current[scope] != expected
        for scope, expected in request.expected_context_cursors.items()
    ):
        return None
    updated: dict[ContextScope, int] = {**current, **request.context_cursors}
    return min(updated.values()), updated
