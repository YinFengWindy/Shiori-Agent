"""Validate and commit prepared memory consolidation under session ownership."""

import asyncio
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from session.store.common import ContextScope
from session.maintenance_progress import MaintenanceProgress, message_prefix_stamp

from .manager import _ManagerCoreMixin
from .models import effective_context_cursors


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

    expected_ownership: str | None = None
    expected_generation: int | None = None
    consumer_payload: dict[str, Any] = field(default_factory=dict)
    updates_recent_context: bool = False
    expected_prefix_stamp: str = ""

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
            session = self.get_or_create(request.session_key)
            progress = self.maintenance_progress(session, persist=True)
            from conversation.context_scope import role_session_user_threads
            from session.maintenance_progress import ownership_key

            live_ownership = ownership_key(
                role_session_user_threads(self.workspace, request.session_key)
            )
            if request.expected_ownership is not None and (
                request.expected_ownership != live_ownership
                or request.expected_ownership != progress.ownership
                or request.expected_generation != progress.generation
            ):
                return False
            messages = self._store.fetch_session_messages(request.session_key)
            meta = self._store.get_session_meta(request.session_key)
            expected = request.expected_message_ids
            if (
                meta is None
                or not expected
                or not all(expected)
                or tuple(str(message["id"]) for message in messages[: len(expected)])
                != expected
                or (
                    request.expected_prefix_stamp
                    and message_prefix_stamp(messages[: len(expected)])
                    != request.expected_prefix_stamp
                )
            ):
                return False
            next_cursors = _next_cursors(request, meta)
            if next_cursors is None:
                return False
            last_consolidated, context_cursors = next_cursors
            # Prepare a private next state. A storage failure must not publish a
            # cursor/version change into the already shared Session cache.
            progress = MaintenanceProgress.load(progress.dump())

            async def finish_commit() -> None:
                await write_memory()
                if (
                    ownership_key(
                        role_session_user_threads(self.workspace, request.session_key)
                    )
                    != live_ownership
                ):
                    raise RuntimeError("记忆写入期间身份归属已变化，未推进记忆进度")
                progress.memory_version += 1
                if request.updates_recent_context:
                    progress.recent_context_version += 1
                    progress.recent_context_source_ids = list(
                        request.expected_message_ids
                    )
                previous = progress.pending_consumers
                if previous:
                    # Unfinished consumer work from an earlier commit stays queued
                    # ahead of this one instead of being overwritten.
                    request.consumer_payload["backlog"] = [
                        *previous.get("backlog", ()),
                        {k: v for k, v in previous.items() if k != "backlog"},
                    ]
                progress.pending_consumers = request.consumer_payload
                with self._store.transaction():
                    self._store.write_maintenance_progress(
                        request.session_key, progress.dump(), commit=False
                    )
                    self._store.update_last_consolidated(
                        request.session_key,
                        last_consolidated,
                        context_cursors=context_cursors,
                        commit=False,
                    )
                session = self._cache.get(request.session_key)
                if session is not None:
                    session.set_consolidation_cursors(
                        last_consolidated, context_cursors
                    )
                    session.maintenance_progress = progress
                await self._complete_memory_consumers(
                    request.session_key,
                    progress,
                    publish_committed,
                )

            await _finish_shielded(finish_commit())
            return True


async def _finish_shielded(operation: Awaitable[None]) -> None:
    """Defer repeated cancellation until started writes and consumers settle."""
    pending = asyncio.gather(operation, return_exceptions=True)
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


def _next_cursors(
    request: ConsolidationCommitRequest, meta: dict[str, Any]
) -> tuple[int, dict[ContextScope, int] | None] | None:
    """校验提交时看到的游标仍是准备时的值，返回提交后的低水位与按上下文游标。

    游标已被别的提交或撤销改动时返回 None（过时草稿，不产生任何副作用）。按上下文
    提交只比较本次推进的那些上下文，另一类上下文的游标怎么变都不影响本次提交。
    """
    stored_last = int(meta["last_consolidated"])
    if not request.context_cursors:
        if meta["context_cursors"] is not None:
            raise ValueError("会话已按上下文记录整理游标，必须按上下文提交")
        if (
            request.last_consolidated is None
            or stored_last != request.expected_last_consolidated
        ):
            return None
        return request.last_consolidated, None
    current = effective_context_cursors(meta["context_cursors"], stored_last)
    if any(
        current[scope] != expected
        for scope, expected in request.expected_context_cursors.items()
    ):
        return None
    updated: dict[ContextScope, int] = {**current, **request.context_cursors}
    return min(updated.values()), updated
