"""旁听记录按群整理（#541）：一批记录整理成什么、写到哪里。

每条旁听记录入库后（``listening_trigger``）检查该群是否到了整理的时候
（``listening_window`` 的触发规则），到了就在后台整理这一批：

- 群友的发言（外部段）按角色会话整理外部段的同一套流程，产出该群的最近动态、
  群笔记更新与成员档案更新（含一行速记），经 ``commit_external_layers`` 写入，
  与角色会话整理共用乐观校验；
- 用户本人在群里的发言（``belongs_to_user``）按 #496 走用户层：提取 HISTORY 与
  PENDING、写入角色记忆目录，再交给记忆引擎。RECENT_CONTEXT 只取用户上下文会话
  的消息，旁听整理不碰它；
- 最后只推进该群的旁听游标（``ListeningCursors``），角色会话的整理游标不变。

旁听消息不驱动孤独值、在场与关系快照，所以整理后不跑角色会话的整理后钩子。
同一个群的整理按群串行（锁跨配置版本共享）；不同群、以及角色会话的整理互不
等待，群笔记与成员档案的并发写入由提交时的乐观校验兜住：被别处改过就按过期
放弃、游标不动，该群下一条记录入库时重来。
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from conversation.context_scope import load_user_context_threads
from conversation.listening_store import GroupListeningStore, ListeningMessage
from core.memory.external_writes import commit_external_layers
from session.manager.helpers import role_session_key

from .contracts import (
    ConsolidateResult,
    ExternalLayerUpdates,
    _ConsolidationFailure,
    _ConsolidationWindow,
)
from .external_segment import group_external_threads
from .formatting import (
    _build_consolidation_source_ref,
    _format_conversation_for_consolidation,
    _is_nsfw_memory_enabled_session,
    _split_consolidation_window,
)
from .listening_window import (
    LISTENING_BATCH_SIZE,
    listening_session_message,
    select_listening_batch,
)
from .runtime import resolve_markdown_store
from .user_layer import append_user_layer, publish_user_layer

if TYPE_CHECKING:
    from collections.abc import Callable

    from bus.event_bus import EventBus
    from core.memory.group_environment import GroupEnvironment
    from core.memory.member_profiles import MemberProfiles
    from core.roles import RoleStore

    from .consolidation import _MarkdownConsolidationWorker


@dataclass(frozen=True)
class _ListeningDraft:
    """一批旁听记录准备好的整理产出，提交时写入。

    ``cursor`` 是准备前看到的该群游标，``up_to`` 是这批最后一条记录的 ``seq``，
    提交后的游标；用户层产物只来自其中用户本人的发言，``conversation`` 为空表示没有。
    """

    role_id: str
    cursor: int
    up_to: int
    source_ref: str
    history_entry_payloads: list[tuple[str, int]]
    pending_items: str
    conversation: str
    external: ExternalLayerUpdates


class ListeningConsolidation:
    """Consolidates each group's listening records, one group at a time.

    Owned by ``MarkdownMemoryMaintenance``, which shares its LLM worker and
    member profiles and binds the runtime collaborators (``bind``). The
    listening records and cursors are read from the bound group
    environment's conversation store. ``ListeningTrigger`` calls
    ``consolidate`` as records are stored.
    """

    def __init__(
        self,
        *,
        worker: "_MarkdownConsolidationWorker",
        workspace: Path,
        member_profiles: "MemberProfiles",
        event_bus: "EventBus | None",
    ) -> None:
        self._worker = worker
        self._workspace = workspace
        self._member_profiles = member_profiles
        self._event_bus = event_bus
        self._get_session: Callable[[str], object] | None = None
        self._group_environment: GroupEnvironment | None = None
        self._runtime_roles: RoleStore | None = None
        # 每群一把整理锁，跨配置版本共享（``share_execution``）。
        self._locks: dict[str, asyncio.Lock] = {}

    def bind(
        self,
        *,
        get_session: "Callable[[str], object]",
        group_environment: "GroupEnvironment",
        runtime_roles: "RoleStore",
    ) -> None:
        """Binds the runtime collaborators, as ``bind_lifecycle`` does for sessions.

        ``get_session`` gives the role's shared session (for its memory
        settings), ``group_environment`` where group notes and recent activity
        live, ``runtime_roles`` the identity bindings that recognise the user.
        """
        self._get_session = get_session
        self._group_environment = group_environment
        self._runtime_roles = runtime_roles

    def share_execution(self, previous: ListeningConsolidation) -> None:
        """Serializes each group's consolidation across configuration versions."""
        self._locks = previous._locks

    async def consolidate(self, thread_id: str) -> ConsolidateResult:
        """Consolidates the group's due batches in turn until none is due.

        Returns the combined count of committed records (mode ``markdown``),
        ``skipped`` when nothing was due or the batch went stale, or the
        failed step (mode ``failed``); batches committed before a failure stay.
        """
        lock = self._locks.setdefault(thread_id, asyncio.Lock())
        consolidated = 0
        async with lock:
            while True:
                outcome = await self._consolidate_batch(thread_id)
                if outcome.trace.get("mode") != "markdown":
                    break
                consolidated += outcome.consolidated_count
        if outcome.trace.get("mode") == "failed" or not consolidated:
            return outcome
        return ConsolidateResult(
            consolidated_count=consolidated, trace={"mode": "markdown"}
        )

    async def _consolidate_batch(self, thread_id: str) -> ConsolidateResult:
        """整理该群到期的一批记录并提交；没有到期的批次时跳过。"""
        store = self._require_store()
        cursor = store.cursors.get(thread_id)
        batch = select_listening_batch(
            store.after(thread_id, cursor, LISTENING_BATCH_SIZE)
        )
        if not batch:
            return ConsolidateResult(trace={"mode": "skipped"})
        draft = await self._prepare(thread_id, cursor, batch)
        if isinstance(draft, _ConsolidationFailure):
            return ConsolidateResult(
                trace={
                    "mode": "failed",
                    "step": draft.step,
                    "error": draft.error,
                    "elapsed_ms": draft.elapsed_ms,
                }
            )
        if not await self._commit(thread_id, draft):
            return ConsolidateResult(trace={"mode": "skipped", "reason": "stale"})
        return ConsolidateResult(
            consolidated_count=len(batch), trace={"mode": "markdown"}
        )

    async def _prepare(
        self, thread_id: str, cursor: int, batch: list[ListeningMessage]
    ) -> _ListeningDraft | _ConsolidationFailure:
        """把一批记录拆成用户本人段与外部段，分别走用户层与群环境 / 成员层的提取。"""
        group_environment, runtime_roles, get_session = self._require_bound()
        thread = group_environment.conversation_store.get_thread(thread_id)
        if thread is None:
            raise ValueError(f"旁听记录所属的会话不存在：{thread_id}")
        role_id = thread.role_id
        nsfw_memory_enabled = _is_nsfw_memory_enabled_session(
            get_session(role_session_key(role_id))
        )
        user_threads = load_user_context_threads(self._workspace, role_id)
        up_to = batch[-1].seq
        if up_to is None:
            raise ValueError("只有已入库的旁听记录才能整理")
        window = _ConsolidationWindow(
            old_messages=[listening_session_message(message) for message in batch],
            keep_count=0,
            consolidate_up_to=up_to,
        )
        segments = _split_consolidation_window(window, user_threads)
        # 用户本人在群里的发言按 #496 进用户层，带群名标注。
        conversation = _format_conversation_for_consolidation(
            segments.user_messages,
            nsfw_memory_enabled=nsfw_memory_enabled,
            user_threads=user_threads,
        )
        history_entry_payloads: list[tuple[str, int]] = []
        pending_items = ""
        if conversation:
            extracted = await self._worker.extract_user_layer(
                conversation,
                resolve_markdown_store(workspace=self._workspace, role_id=role_id),
            )
            if isinstance(extracted, _ConsolidationFailure):
                return extracted
            history_entry_payloads, pending_items = extracted
        external = ExternalLayerUpdates()
        external_threads = group_external_threads(
            window, segments, runtime_roles.bound_user_senders(role_id)
        )
        if external_threads:
            extracted_external = await self._worker.extract_external_layers(
                external_threads,
                group_environment=group_environment,
                member_profiles=self._member_profiles,
                role_id=role_id,
                nsfw_memory_enabled=nsfw_memory_enabled,
            )
            if isinstance(extracted_external, _ConsolidationFailure):
                return extracted_external
            external = extracted_external
        return _ListeningDraft(
            role_id=role_id,
            cursor=cursor,
            up_to=up_to,
            source_ref=_build_consolidation_source_ref(segments.user_messages),
            history_entry_payloads=history_entry_payloads,
            pending_items=pending_items,
            conversation=conversation,
            external=external,
        )

    async def _commit(self, thread_id: str, draft: _ListeningDraft) -> bool:
        """写入产出并推进该群的旁听游标；过期时什么都不写并返回 False。

        群笔记与成员档案先写：准备后被别处改过就在任何写入之前放弃，游标不动。
        用户层按 ``source_ref`` 幂等追加，所以游标推进前中断后重来也不会重复。
        """
        store = self._require_store()
        group_environment, _runtime_roles, _get_session = self._require_bound()
        if store.cursors.get(thread_id) != draft.cursor:
            return False
        external = draft.external
        if external.group_environment or external.member_profiles:
            written = await asyncio.to_thread(
                commit_external_layers,
                group_environment,
                self._member_profiles,
                draft.role_id,
                environment_updates=external.group_environment,
                member_updates=external.member_profiles,
                snapshot=external.snapshot,
                updated_at=datetime.now().astimezone(),
            )
            if not written:
                return False
        await asyncio.to_thread(
            append_user_layer,
            resolve_markdown_store(workspace=self._workspace, role_id=draft.role_id),
            [entry for entry, _ in draft.history_entry_payloads],
            draft.pending_items,
            draft.source_ref,
        )
        if not store.cursors.advance(thread_id, expected=draft.cursor, to=draft.up_to):
            return False
        await publish_user_layer(
            self._event_bus,
            role_id=draft.role_id,
            history_entry_payloads=draft.history_entry_payloads,
            source_ref=draft.source_ref,
            conversation=draft.conversation,
            scope_channel="",
            scope_chat_id="",
        )
        return True

    def _require_store(self) -> GroupListeningStore:
        return self._require_bound()[0].conversation_store.listening

    def _require_bound(
        self,
    ) -> tuple["GroupEnvironment", "RoleStore", "Callable[[str], object]"]:
        if (
            self._group_environment is None
            or self._runtime_roles is None
            or self._get_session is None
        ):
            raise RuntimeError("memory lifecycle is not bound")
        return self._group_environment, self._runtime_roles, self._get_session
