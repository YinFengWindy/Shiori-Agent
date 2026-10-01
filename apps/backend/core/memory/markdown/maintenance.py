"""Markdown memory 的后台维护队列与 consolidation 提交。"""

from __future__ import annotations

import asyncio
import logging
from collections import deque
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import TYPE_CHECKING, Any

from bus.events_lifecycle import (
    NOT_USER_AUTHORED_KEY,
    SKIP_POST_MEMORY_KEY,
    TurnCommitted,
)
from conversation.context_scope import (
    ContextView,
    UserContextThreads,
    role_context_views,
    role_session_user_threads,
)
from core.memory.external_writes import commit_external_layers
from core.memory.member_profiles import MemberProfiles
from session.manager.consolidation import ConsolidationCommitRequest
from session.manager.models import consolidation_cursor
from session.manager.consumers import MemoryConsumersFailedError
from session.manager.window import WindowPreparation
from session.maintenance_progress import ownership_key, message_prefix_stamp
from session.store.common import ContextScope

from .consolidation import _MarkdownConsolidationWorker
from .contracts import (
    ConsolidateRequest,
    ConsolidateResult,
    MemoryLifecycleBindRequest,
    RefreshRecentTurnsRequest,
    _ConsolidationDraft,
    ConsolidationFailure,
)
from .listening import ListeningConsolidation
from .listening_trigger import ListeningTrigger
from .formatting import (
    _format_consolidation_error,
    _select_consolidation_window,
    _session_role_id,
)
from .runtime import MarkdownMemoryStore, resolve_markdown_store
from .user_layer import append_user_layer, publish_user_layer

if TYPE_CHECKING:
    from bus.event_bus import EventBus
    from agent.provider import LLMProvider
    from core.memory.group_environment import GroupEnvironment
    from core.roles import RoleStore

logger = logging.getLogger("memory.markdown")


class _StaleExternalLayers(Exception):
    """准备后群笔记或成员档案已被别处（小手机）改过：本次整理按过期处理，不提交。"""


class MarkdownMemoryMaintenance:
    def __init__(
        self,
        *,
        store: MarkdownMemoryStore,
        provider: "LLMProvider",
        model: str,
        keep_count: int,
        event_bus: "EventBus | None" = None,
        recent_context_provider: "LLMProvider | None" = None,
        recent_context_model: str | None = None,
    ) -> None:
        self._store = store
        self._workspace = store.memory_dir.parent
        # 成员层（#498）只依赖工作区路径，整理读写成员档案都经由它。
        self._member_profiles = MemberProfiles(self._workspace)
        self._event_bus = event_bus
        self._worker = _MarkdownConsolidationWorker(
            profile_maint=store,
            provider=provider,
            model=model,
            keep_count=keep_count,
            recent_context_provider=recent_context_provider,
            recent_context_model=recent_context_model,
        )
        # 旁听记录按群整理（#541），与角色会话整理共用提取与成员层。
        self.listening = ListeningConsolidation(
            worker=self._worker,
            workspace=self._workspace,
            member_profiles=self._member_profiles,
            event_bus=event_bus,
        )
        self.listening_trigger = ListeningTrigger(self.listening)
        self._keep_count = keep_count
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
        self._group_environment: GroupEnvironment | None = None
        self._runtime_roles: RoleStore | None = None
        self._maintenance_queues: dict[str, deque[str]] = {}
        self._maintenance_tasks: dict[str, asyncio.Task[None]] = {}
        self._maintenance_locks: dict[str, asyncio.Lock] = {}
        self._maintenance_failures: dict[str, str] = {}
        self._retry_consumers = None
        self._record_publication = None
        self._record_recent_context = None
        if event_bus is not None:
            event_bus.on(TurnCommitted, self.on_turn_committed)

    def _resolve_store_for_session(self, session: object) -> MarkdownMemoryStore:
        # 角色 ID 与上下文划分同一来源：元数据没有时取 role:<id> 会话键里的。
        return resolve_markdown_store(
            workspace=self._workspace, role_id=_session_role_id(session)
        )

    def _user_threads_for_session(self, session: object) -> UserContextThreads | None:
        """角色共享会话此刻的用户上下文会话，供整理按发送者拆段。

        只有 ``role:<id>`` 会话混存多个会话的消息；其他会话没有划分，返回 None。
        """
        return role_session_user_threads(
            self._workspace, str(getattr(session, "key", "") or "")
        )

    def _window_plans(
        self, session: object, *, scope: ContextScope | None = None
    ) -> list[tuple[ContextView, ...]]:
        """平时整理要分别尝试的窗口：每项是一次整理推进游标的上下文。

        非角色会话只有一项（空元组，推进 last_consolidated）；角色会话每类上下文
        各一项、各自判断与提交（#523），``scope`` 给出时只看这一类。
        """
        user_threads = self._user_threads_for_session(session)
        if user_threads is None:
            return [()]
        return [
            (view,)
            for view in role_context_views(user_threads)
            if scope is None or view.scope == scope
        ]

    def bind_lifecycle(self, request: MemoryLifecycleBindRequest) -> None:
        self._get_session = request.get_session
        self._commit_consolidation = request.commit_consolidation
        self._after_consolidation = request.after_consolidation
        self._retry_consumers = request.retry_consumers
        self._record_publication = request.record_publication
        self._record_recent_context = request.record_recent_context
        self._group_environment = request.group_environment
        self._runtime_roles = request.runtime_roles
        if request.group_environment is not None and request.runtime_roles is not None:
            self.listening.bind(
                get_session=request.get_session,
                group_environment=request.group_environment,
                runtime_roles=request.runtime_roles,
            )

    def share_execution(self, previous: MarkdownMemoryMaintenance) -> None:
        """Serializes writes to shared sessions across configuration versions."""
        self._maintenance_locks = previous._maintenance_locks
        self.listening.share_execution(previous.listening)

    async def drain(self) -> None:
        """Waits for already queued maintenance before its providers are closed."""
        await self.listening_trigger.drain()
        while self._maintenance_tasks:
            await asyncio.gather(
                *tuple(self._maintenance_tasks.values()), return_exceptions=True
            )
            await asyncio.sleep(0)

    def on_turn_committed(self, event: TurnCommitted) -> None:
        extra = event.extra or {}
        # 群友回合只是不给引擎抽取，整理照常触发，由整理按发送者拆段。
        if extra.get(SKIP_POST_MEMORY_KEY) and not extra.get(NOT_USER_AUTHORED_KEY):
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

    async def ensure_memory_for_window(
        self, prepared: WindowPreparation
    ) -> ConsolidateResult:
        """Complete every unprocessed category member through the window's cut.

        An external window can contain interleaved groups. Extract the owning
        external category prefix, so advancing its cursor cannot skip another group.
        """
        if self._get_session is None:
            raise RuntimeError("memory lifecycle is not bound")
        session = self._get_session(prepared.session_key)
        if (
            ownership_key(self._user_threads_for_session(session)) != prepared.ownership
            or tuple(
                str(m.get("id") or "")
                for m in session.messages[: len(prepared.expected_message_ids)]
            )
            != prepared.expected_message_ids
            or message_prefix_stamp(
                session.messages[: len(prepared.expected_message_ids)]
            )
            != prepared.prefix_stamp
        ):
            return ConsolidateResult(
                trace={"mode": "failed", "step": "stale", "memory_committed": False}
            )
        result = await self.consolidate(
            ConsolidateRequest(
                session=session,
                scope=prepared.view.scope if prepared.view else None,
                through_index=prepared.stop,
            )
        )
        cursor = consolidation_cursor(
            session, prepared.view.scope if prepared.view else None
        )
        covered_ids = {
            str(message.get("id") or "") for message in session.messages[:cursor]
        }
        result.trace["memory_committed"] = set(prepared.removed_message_ids).issubset(
            covered_ids
        )
        return result

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
        progress = getattr(session, "maintenance_progress", None)
        if progress is not None and progress.pending_consumers:
            return True
        return any(
            _select_consolidation_window(
                session,
                keep_count=self._keep_count,
                consolidation_min_new_messages=self._consolidation_min_new_messages,
                archive_all=False,
                force=False,
                views=views,
            )
            is not None
            for views in self._window_plans(session)
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
        """按窗口逐个整理并提交；角色会话每类上下文各自一个窗口（#523）。

        带 ``scope`` 的请求（包括回合预算触发的 force）只整理并推进这一类上下文；
        只有 archive_all 与不带 scope 的全量 force 把两类放进同一个窗口一起推进。
        某个窗口失败时立即返回失败，此前已提交的窗口保留。
        """
        session = request.session
        if self._retry_consumers is not None:
            try:
                await self._retry_consumers(
                    str(session.key),
                    lambda payload: self._consume_payload(session, payload),
                )
            except MemoryConsumersFailedError as exc:
                return ConsolidateResult(
                    trace={
                        "mode": "failed",
                        "step": "consumers",
                        "memory_committed": True,
                        "error": str(exc),
                    }
                )
        user_threads = self._user_threads_for_session(session)
        if user_threads is not None and (
            request.archive_all or (request.force and request.scope is None)
        ):
            plans = [role_context_views(user_threads)]
        else:
            plans = self._window_plans(session, scope=request.scope)
        committed: list[ConsolidateResult] = []
        outcome = ConsolidateResult(trace={"mode": "skipped"})
        for views in plans:
            outcome = await self._consolidate_window(request, views, user_threads)
            if outcome.trace.get("mode") == "failed":
                break
            if outcome.trace.get("mode") == "markdown":
                committed.append(outcome)
        if outcome.trace.get("mode") == "failed" or not committed:
            return outcome
        return ConsolidateResult(
            consolidated_count=sum(item.consolidated_count for item in committed),
            trace={
                "mode": "markdown",
                "source_refs": [item.trace["source_ref"] for item in committed],
            },
        )

    async def _consolidate_window(
        self,
        request: ConsolidateRequest,
        views: tuple[ContextView, ...],
        user_threads: UserContextThreads | None,
    ) -> ConsolidateResult:
        """准备并条件提交一个窗口，只推进 ``views`` 这些上下文的游标。"""
        session_key = str(getattr(request.session, "key", "") or "")
        # Capture IDs before preparation yields; undo may mutate the shared Session.
        expected_ids = tuple(
            str(message.get("id") or "")
            for message in getattr(request.session, "messages", [])
        )
        expected_cursor = int(getattr(request.session, "last_consolidated", 0))
        expected_prefix_stamp = message_prefix_stamp(
            getattr(request.session, "messages", [])
        )
        # 整理的提交、群环境层写入与身份绑定都由 bind_lifecycle 接入，未接入时直接失败。
        commit = self._commit_consolidation
        group_environment = self._group_environment
        runtime_roles = self._runtime_roles
        if commit is None or group_environment is None or runtime_roles is None:
            raise RuntimeError("memory lifecycle is not bound")
        expected_context_cursors: dict[ContextScope, int] = {
            view.scope: consolidation_cursor(request.session, view.scope)
            for view in views
        }
        progress = getattr(request.session, "maintenance_progress", None)
        expected_generation = progress.generation if progress is not None else None
        expected_ownership = ownership_key(user_threads)
        draft = await self._worker.prepare_consolidation(
            request.session,
            archive_all=request.archive_all,
            force=request.force,
            through_index=request.through_index,
            user_threads=user_threads,
            group_environment=group_environment,
            views=views,
            member_profiles=self._member_profiles,
            bound_senders=runtime_roles.bound_user_senders(
                _session_role_id(request.session)
            ),
        )
        if draft is None:
            if session_key:
                _ = self._maintenance_failures.pop(session_key, None)
            return ConsolidateResult(trace={"mode": "skipped"})
        if isinstance(draft, ConsolidationFailure):
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

        async def write_memory() -> None:
            # 群笔记与档案先写：准备后被改过时在任何写入之前放弃，游标也不推进。
            await self._write_external_layers(request.session, draft, group_environment)
            await self._commit_markdown_draft(request.session, draft)

        payload = {
            "role_id": _session_role_id(request.session),
            "history_entry_payloads": draft.history_entry_payloads,
            "source_ref": draft.source_ref,
            "conversation": draft.conversation,
            "scope_channel": draft.scope_channel,
            "scope_chat_id": draft.scope_chat_id,
        }

        async def publish_committed() -> None:
            await self._consume_payload(request.session, payload)

        try:
            committed = await commit(
                _commit_request(
                    session_key,
                    expected_ids,
                    draft,
                    expected_cursor=expected_cursor,
                    expected_context_cursors=expected_context_cursors,
                    expected_ownership=(
                        expected_ownership if progress is not None else None
                    ),
                    expected_generation=expected_generation,
                    consumer_payload=payload,
                    expected_prefix_stamp=expected_prefix_stamp,
                ),
                write_memory,
                publish_committed,
            )
        except _StaleExternalLayers:
            committed = False
        except MemoryConsumersFailedError as exc:
            self._maintenance_failures[session_key] = str(exc)
            return ConsolidateResult(
                trace={
                    "mode": "failed",
                    "step": "consumers",
                    "memory_committed": True,
                    "error": str(exc),
                }
            )
        if not committed:
            return ConsolidateResult(trace={"mode": "skipped", "reason": "stale"})
        if session_key:
            _ = self._maintenance_failures.pop(session_key, None)
        return ConsolidateResult(
            consolidated_count=len(draft.window.old_messages),
            trace={"mode": "markdown", "source_ref": draft.source_ref},
        )

    async def _consume_payload(self, session: object, payload: dict[str, Any]) -> None:
        if not payload.get("published"):
            publication = {
                key: value for key, value in payload.items() if key != "published"
            }
            publication["history_entry_payloads"] = [
                (entry, weight) for entry, weight in payload["history_entry_payloads"]
            ]
            await publish_user_layer(
                self._event_bus,
                **publication,
            )
            if self._record_publication is not None:
                self._record_publication(session.key, payload)
        if self._after_consolidation is not None:
            await self._after_consolidation(session)

    async def _commit_markdown_draft(
        self,
        session: object,
        draft: "_ConsolidationDraft",
    ) -> None:
        await append_user_layer(
            self._resolve_store_for_session(session),
            draft.history_entry_payloads,
            draft.pending_items,
            draft.source_ref,
            recent_context_text=draft.recent_context_text,
        )

    async def _write_external_layers(
        self,
        session: object,
        draft: _ConsolidationDraft,
        group_environment: "GroupEnvironment",
    ) -> None:
        """把外部段整理出的群环境层与成员档案更新写入；不经过记忆引擎。

        准备时读到的群笔记与档案在此期间被改过（小手机编辑）时什么都不写，抛
        ``_StaleExternalLayers`` 让本次整理按过期处理，下次用新内容重来。
        """
        if not draft.group_environment_updates and not draft.member_profile_updates:
            return
        written = await asyncio.to_thread(
            commit_external_layers,
            group_environment,
            self._member_profiles,
            _session_role_id(session),
            environment_updates=draft.group_environment_updates,
            member_updates=draft.member_profile_updates,
            snapshot=draft.external_snapshot,
            updated_at=datetime.now().astimezone(),
        )
        if not written:
            raise _StaleExternalLayers

    async def refresh_recent_turns(
        self,
        request: RefreshRecentTurnsRequest,
    ) -> None:
        source_ids = tuple(str(m.get("id") or "") for m in request.session.messages)
        ownership = ownership_key(self._user_threads_for_session(request.session))
        await self._worker.refresh_recent_turns(
            session=request.session,
            profile_maint=self._resolve_store_for_session(request.session),
            user_threads=self._user_threads_for_session(request.session),
        )
        if self._record_recent_context is not None:
            await self._record_recent_context(
                request.session.key, source_ids, ownership
            )


def _commit_request(
    session_key: str,
    expected_ids: tuple[str, ...],
    draft: _ConsolidationDraft,
    *,
    expected_cursor: int,
    expected_context_cursors: dict[ContextScope, int],
    expected_ownership: str | None,
    expected_generation: int | None,
    consumer_payload: dict[str, Any],
    expected_prefix_stamp: str,
) -> ConsolidationCommitRequest:
    """把草稿要推进的游标写成条件提交请求，准备前看到的游标是预期值。

    非角色会话推进 last_consolidated；角色会话只推进窗口所属上下文的游标，
    只进不退，archive_all 则全部归零。
    """
    window = draft.window
    common = {
        "expected_ownership": expected_ownership,
        "expected_generation": expected_generation,
        "consumer_payload": consumer_payload,
        "updates_recent_context": bool(draft.recent_context_text),
        "expected_prefix_stamp": expected_prefix_stamp,
    }
    if not window.scopes:
        return ConsolidationCommitRequest(
            session_key=session_key,
            expected_message_ids=expected_ids,
            **common,
            expected_last_consolidated=expected_cursor,
            last_consolidated=0 if draft.archive_all else window.consolidate_up_to,
        )
    return ConsolidationCommitRequest(
        session_key=session_key,
        expected_message_ids=expected_ids,
        **common,
        expected_context_cursors={
            scope: expected_context_cursors[scope] for scope in window.scopes
        },
        context_cursors={
            scope: (
                0
                if draft.archive_all
                else max(expected_context_cursors[scope], window.consolidate_up_to)
            )
            for scope in window.scopes
        },
    )
