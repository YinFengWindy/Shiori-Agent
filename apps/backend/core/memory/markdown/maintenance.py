"""Markdown memory 的后台维护队列与 consolidation 提交。"""

from __future__ import annotations

import asyncio
import logging
from collections import deque
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

from bus.events_lifecycle import TurnCommitted
from core.memory.events import ConsolidationCommitted
from session.manager.consolidation import ConsolidationCommitRequest

from .consolidation import _MarkdownConsolidationWorker
from .contracts import (
    ConsolidateRequest,
    ConsolidateResult,
    MemoryLifecycleBindRequest,
    RefreshRecentTurnsRequest,
    _ConsolidationDraft,
    _ConsolidationFailure,
)
from .formatting import (
    _append_entries_to_journal,
    _format_consolidation_error,
    _select_consolidation_window,
    _estimate_session_input_tokens,
)
from .runtime import MarkdownMemoryStore, resolve_markdown_store

if TYPE_CHECKING:
    from bus.event_bus import EventBus
    from agent.provider import LLMProvider

logger = logging.getLogger("memory.markdown")


def _session_input_over_budget(
    session: object, threshold: int, current_content: str = ""
) -> bool:
    return (
        threshold > 0
        and _estimate_session_input_tokens(session, current_content) >= threshold
    )


class MarkdownMemoryMaintenance:
    def __init__(
        self,
        *,
        store: MarkdownMemoryStore,
        provider: "LLMProvider",
        model: str,
        keep_count: int,
        input_token_threshold: int = 75000,
        event_bus: "EventBus | None" = None,
        recent_context_provider: "LLMProvider | None" = None,
        recent_context_model: str | None = None,
    ) -> None:
        self._store = store
        self._event_bus = event_bus
        self._worker = _MarkdownConsolidationWorker(
            profile_maint=store,
            provider=provider,
            model=model,
            keep_count=keep_count,
            input_token_threshold=input_token_threshold,
            recent_context_provider=recent_context_provider,
            recent_context_model=recent_context_model,
        )
        self._keep_count = keep_count
        self._input_token_threshold = max(0, int(input_token_threshold))
        self._consolidation_min_new_messages = max(5, keep_count // 2)
        self._get_session: Callable[[str], object] | None = None
        self._commit_consolidation: (
            Callable[
                [
                    ConsolidationCommitRequest,
                    Callable[[], Awaitable[None]],
                    Callable[[], Awaitable[None]],
                ],
                Awaitable[bool],
            ]
            | None
        ) = None
        self._after_consolidation: Callable[[object], Awaitable[None]] | None = None
        self._maintenance_queues: dict[str, deque[str]] = {}
        self._maintenance_tasks: dict[str, asyncio.Task[None]] = {}
        self._maintenance_locks: dict[str, asyncio.Lock] = {}
        self._maintenance_failures: dict[str, str] = {}
        if event_bus is not None:
            event_bus.on(TurnCommitted, self.on_turn_committed)

    def _resolve_store_for_session(self, session: object) -> MarkdownMemoryStore:
        metadata = getattr(session, "metadata", {})
        return resolve_markdown_store(
            workspace=self._store.memory_dir.parent,
            session_metadata=metadata if isinstance(metadata, dict) else None,
        )

    def bind_lifecycle(self, request: MemoryLifecycleBindRequest) -> None:
        self._get_session = request.get_session
        self._commit_consolidation = request.commit_consolidation
        self._after_consolidation = request.after_consolidation

    def share_execution(self, previous: MarkdownMemoryMaintenance) -> None:
        """Serializes writes to shared sessions across configuration versions."""
        self._maintenance_locks = previous._maintenance_locks

    async def drain(self) -> None:
        """Waits for already queued maintenance before its providers are closed."""
        while self._maintenance_tasks:
            await asyncio.gather(
                *tuple(self._maintenance_tasks.values()), return_exceptions=True
            )
            await asyncio.sleep(0)

    def on_turn_committed(self, event: TurnCommitted) -> None:
        if bool((event.extra or {}).get("skip_post_memory")):
            return
        self._enqueue_maintenance(event.session_key)

    def request_background_consolidation(self, session_key: str) -> None:
        """非阻塞请求指定会话执行后台记忆整理。"""
        if self.get_consolidation_failure(session_key) is not None:
            return
        task = self._maintenance_tasks.get(session_key)
        if task is not None and not task.done():
            return
        self._enqueue_maintenance(session_key)

    def get_consolidation_failure(self, session_key: str) -> str | None:
        """返回指定会话最近一次后台记忆整理的明确失败原因。"""
        return self._maintenance_failures.get(session_key)

    async def ensure_consolidation(
        self, session_key: str, current_content: str = ""
    ) -> bool:
        """Finish token-triggered consolidation before sending a model request."""
        if self._get_session is None or self._commit_consolidation is None:
            return False
        existing = self._maintenance_tasks.get(session_key)
        if existing is not None and not existing.done():
            try:
                await existing
            except Exception:
                # The queue records the definitive failure; the caller must
                # stop before issuing a model request instead of leaking the
                # background task's implementation exception.
                return False
        session = self._get_session(session_key)
        if session is None:
            return False
        for force in (False, True):
            result = await self.consolidate(
                ConsolidateRequest(
                    session=session,
                    force=force,
                    current_content=current_content,
                )
            )
            if result.trace.get("mode") == "failed":
                return False
            if not _session_input_over_budget(
                session, self._input_token_threshold, current_content
            ):
                return True
            if result.trace.get("mode") != "markdown":
                return False
        return not _session_input_over_budget(
            session, self._input_token_threshold, current_content
        )

    def _enqueue_maintenance(self, session_key: str) -> None:
        if self._get_session is None or self._commit_consolidation is None:
            return
        queue = self._maintenance_queues.setdefault(session_key, deque())
        queue.append(session_key)
        if session_key in self._maintenance_tasks:
            return
        task = asyncio.create_task(
            self._run_maintenance_queue(session_key),
            name=f"markdown-memory-maintenance:{session_key}",
        )
        self._maintenance_tasks[session_key] = task
        task.add_done_callback(lambda t: self._on_maintenance_done(t, session_key))

    async def _run_maintenance_queue(self, session_key: str) -> None:
        lock = self._maintenance_locks.setdefault(session_key, asyncio.Lock())
        async with lock:
            while True:
                queue = self._maintenance_queues.get(session_key)
                if not queue:
                    return
                _ = queue.popleft()
                session = self._get_session(session_key) if self._get_session else None
                if session is None:
                    return
                if self._should_consolidate_session(session):
                    try:
                        result = await self._consolidate_unlocked(
                            ConsolidateRequest(session=session)
                        )
                    except Exception as exc:
                        self._maintenance_failures[session_key] = (
                            _format_consolidation_error(exc)
                        )
                        queue.clear()
                        raise
                    if result.trace.get("mode") == "failed":
                        queue.clear()
                        return
                else:
                    await self.refresh_recent_turns(
                        RefreshRecentTurnsRequest(session=session)
                    )

    def _on_maintenance_done(
        self,
        task: asyncio.Task[None],
        session_key: str,
    ) -> None:
        if self._maintenance_tasks.get(session_key) is task:
            _ = self._maintenance_tasks.pop(session_key, None)
        if task.cancelled():
            logger.info("markdown memory maintenance cancelled: %s", session_key)
            return
        try:
            exc = task.exception()
        except Exception as e:
            logger.warning(
                "markdown memory maintenance inspect failed: session=%s err=%s",
                session_key,
                e,
            )
            return
        if exc is not None:
            _ = self._maintenance_queues.pop(session_key, None)
            logger.warning(
                "markdown memory maintenance failed: session=%s err=%s",
                session_key,
                exc,
            )
            return
        queue = self._maintenance_queues.get(session_key)
        if queue:
            next_task = asyncio.create_task(
                self._run_maintenance_queue(session_key),
                name=f"markdown-memory-maintenance:{session_key}",
            )
            self._maintenance_tasks[session_key] = next_task
            next_task.add_done_callback(
                lambda t: self._on_maintenance_done(t, session_key)
            )
        else:
            _ = self._maintenance_queues.pop(session_key, None)

    def _should_consolidate_session(self, session: object) -> bool:
        return (
            _select_consolidation_window(
                session,
                keep_count=self._keep_count,
                consolidation_min_new_messages=self._consolidation_min_new_messages,
                input_token_threshold=self._input_token_threshold,
                input_token_estimate=_estimate_session_input_tokens(session),
                archive_all=False,
                force=False,
            )
            is not None
        )

    async def consolidate(self, request: ConsolidateRequest) -> ConsolidateResult:
        session_key = str(getattr(request.session, "key", "") or "")
        if not session_key:
            return await self._consolidate_unlocked(request)
        lock = self._maintenance_locks.setdefault(session_key, asyncio.Lock())
        async with lock:
            return await self._consolidate_unlocked(request)

    async def _consolidate_unlocked(
        self, request: ConsolidateRequest
    ) -> ConsolidateResult:
        session_key = str(getattr(request.session, "key", "") or "")
        # Capture IDs before preparation yields; undo may mutate the shared Session.
        expected_ids = tuple(
            str(message.get("id") or "")
            for message in getattr(request.session, "messages", [])
        )
        expected_cursor = int(getattr(request.session, "last_consolidated", 0))
        draft = await self._worker.prepare_consolidation(
            request.session,
            archive_all=request.archive_all,
            force=request.force,
            input_token_estimate=_estimate_session_input_tokens(
                request.session, request.current_content
            ),
        )
        if draft is None:
            if session_key:
                _ = self._maintenance_failures.pop(session_key, None)
            return ConsolidateResult(trace={"mode": "skipped"})
        if isinstance(draft, _ConsolidationFailure):
            if session_key:
                self._maintenance_failures[session_key] = draft.error
            return ConsolidateResult(
                trace={
                    "mode": "failed",
                    "step": draft.step,
                    "error": draft.error,
                    "elapsed_ms": draft.elapsed_ms,
                }
            )
        commit = self._commit_consolidation
        if commit is None:
            raise RuntimeError("session consolidation commit operation is not bound")

        async def write_memory() -> None:
            await self._commit_markdown_draft(request.session, draft)

        async def publish_committed() -> None:
            await self._publish_consolidation(request.session, draft)

        committed = await commit(
            ConsolidationCommitRequest(
                session_key=session_key,
                expected_message_ids=expected_ids,
                expected_last_consolidated=expected_cursor,
                last_consolidated=(
                    0 if draft.archive_all else draft.window.consolidate_up_to
                ),
            ),
            write_memory,
            publish_committed,
        )
        if not committed:
            return ConsolidateResult(trace={"mode": "skipped", "reason": "stale"})
        await self._run_after_consolidation(request.session)
        if session_key:
            _ = self._maintenance_failures.pop(session_key, None)
        return ConsolidateResult(
            consolidated_count=len(draft.window.old_messages),
            trace={"mode": "markdown", "source_ref": draft.source_ref},
        )

    async def _run_after_consolidation(self, session: object) -> None:
        hook = self._after_consolidation
        if hook is None:
            return
        try:
            await hook(session)
        except Exception as exc:
            logger.warning("markdown memory post-consolidation hook failed: %s", exc)

    async def _commit_markdown_draft(
        self,
        session: object,
        draft: "_ConsolidationDraft",
    ) -> None:
        target_store = self._resolve_store_for_session(session)
        history_entries = [entry for entry, _ in draft.history_entry_payloads]
        if history_entries:
            await asyncio.to_thread(
                target_store.append_history_once,
                "\n".join(history_entries),
                source_ref=draft.source_ref,
                kind="history_entry",
            )
        if draft.pending_items:
            appended = await asyncio.to_thread(
                target_store.append_pending_once,
                draft.pending_items,
                source_ref=draft.source_ref,
                kind="pending_items",
            )
            if appended:
                logger.info(
                    "Markdown memory: appended %d pending_items",
                    len(draft.pending_items.splitlines()),
                )
        target_store.write_recent_context(draft.recent_context_text)
        if history_entries:
            await asyncio.to_thread(
                _append_entries_to_journal,
                target_store,
                history_entries,
                draft.source_ref,
            )

    async def _publish_consolidation(
        self, session: object, draft: _ConsolidationDraft
    ) -> None:
        role_id = str(getattr(session, "metadata", {}).get("role_id") or "").strip()
        if self._event_bus is not None:
            await self._event_bus.emit(
                ConsolidationCommitted(
                    history_entry_payloads=list(draft.history_entry_payloads),
                    source_ref=draft.source_ref,
                    scope_channel=draft.scope_channel,
                    scope_chat_id=draft.scope_chat_id,
                    conversation=draft.conversation,
                    role_id=role_id,
                )
            )

    async def refresh_recent_turns(
        self,
        request: RefreshRecentTurnsRequest,
    ) -> None:
        await self._worker.refresh_recent_turns(
            session=request.session,
            profile_maint=self._resolve_store_for_session(request.session),
        )
