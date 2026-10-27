"""Atomic passive-turn undo owned by the session manager."""

from collections.abc import Sequence
from dataclasses import replace
from typing import TYPE_CHECKING, Any

from session.store.common import ContextScope
from session.maintenance_progress import MaintenanceProgress, message_window_key

from .manager import _ManagerCoreMixin
from .models import effective_context_cursors
from shiori_sdk.core.sessions import PassiveTurn, RollbackResult, TurnChanged
from .undo_selection import (
    _compute_rollback_index,
    _find_last_passive_turn,
    passive_turn,
)

if TYPE_CHECKING:
    from conversation.context_scope import UserContextThreads


class _UndoMixin(_ManagerCoreMixin):
    def last_passive_turn(self, session_key: str) -> PassiveTurn | None:
        """The latest committed passive turn, read without the session write lock.

        ``rollback_last_turn`` selects again under the lock; pass this turn
        as ``expected_turn`` so a turn that changed in between is not deleted
        in its place.
        """
        messages = self._store.fetch_session_messages(session_key)
        target = _find_last_passive_turn(messages)
        if target is None:
            return None
        indices, user_index = target
        return passive_turn(messages, indices, user_index)

    async def rollback_last_turn(
        self,
        session_key: str,
        *,
        expected_turn: PassiveTurn | None = None,
        rollback_source_ids: Sequence[str] = (),
    ) -> RollbackResult | TurnChanged | None:
        """Delete the latest committed passive turn under the session write lock.

        With ``expected_turn``, the turn is deleted only when its anchor and
        every message id still match (memory rolled back exactly that set);
        otherwise nothing is deleted and ``TurnChanged`` is returned. ``rollback_source_ids`` are memory sources
        already rolled back for this turn: they rewind the consolidation cursor
        to the start of their window. Pending message objects stay attached to
        the cached session for queued appends.
        """
        async with self._lock(session_key):
            messages = self._store.fetch_session_messages(session_key)
            target = _find_last_passive_turn(messages)
            if target is None:
                return None
            indices, user_index = target
            turn = passive_turn(messages, indices, user_index)
            if expected_turn is not None and turn != expected_turn:
                return TurnChanged(turn.turn_id)
            deleted_ids = list(turn.message_ids)
            sources = list(rollback_source_ids)
            meta = self._store.get_session_meta(session_key)
            old_last = max(0, int(meta["last_consolidated"])) if meta else 0
            context_cursors: dict[ContextScope, int] | None = None
            # 延迟导入：context_scope 依赖 session.manager，模块级导入会形成循环。
            from conversation.context_scope import role_session_user_threads

            user_threads = role_session_user_threads(self.workspace, session_key)
            if user_threads is not None:
                # 角色会话按上下文各自回退：删掉的消息只让它所属那类上下文的游标
                # 退回重新整理，另一类游标只随删除平移（#523）。
                context_cursors = _rolled_back_context_cursors(
                    user_threads,
                    messages,
                    indices=indices,
                    old_cursors=effective_context_cursors(
                        meta["context_cursors"] if meta else None, old_last
                    ),
                    rollback_source_ids=sources,
                )
                new_last = min(context_cursors.values())
            else:
                new_last = _rolled_back_cursor(
                    messages,
                    indices=indices,
                    scoped_indices=indices,
                    old_cursor=old_last,
                    rollback_source_ids=sources,
                )
            # Include deleted threads even when their last turn disappears.
            thread_ids = {
                str(messages[index].get("thread_id") or "") for index in indices
            }

            # Normalized (legacy-migrated, rebound) progress: shifted cuts must be
            # derived before the deletion moves the memory cursors they freeze.
            progress = _progress_after_undo(
                self.maintenance_progress(self.get_or_create(session_key)),
                messages,
                indices,
                user_threads,
            )

            def refresh_projections() -> None:
                self._store.write_maintenance_progress(
                    session_key, progress.dump(), commit=False
                )
                for thread_id in sorted(thread_ids - {""}):
                    thread = self.conversation_store.get_thread(thread_id)
                    if thread is not None:
                        self._conversation_projector.project_thread(thread)

            # The store validates all IDs before deleting any row or changing cursor.
            _ = self._store.delete_session_messages_and_update_cursor(
                session_key,
                ids=deleted_ids,
                last_consolidated=new_last,
                context_cursors=context_cursors,
                refresh_projections=refresh_projections,
            )
            session = self._cache.get(session_key)
            if session is not None:
                deleted_set = set(deleted_ids)
                session.messages[:] = [
                    message
                    for message in session.messages
                    if message.get("id") not in deleted_set
                ]
                session.set_consolidation_cursors(new_last, context_cursors)
                session.maintenance_progress = progress
            return RollbackResult(
                turn_id=turn.turn_id,
                deleted_ids=turn.message_ids,
                last_consolidated_before=old_last,
                last_consolidated_after=new_last,
            )


def _shifted(cut: int, indices: list[int]) -> int:
    """切点在删除 ``indices`` 后的新下标：只减去它之前被删的条数。"""
    return cut - sum(index < cut for index in indices)


def _progress_after_undo(
    progress: MaintenanceProgress,
    messages: list[dict[str, Any]],
    indices: list[int],
    user_threads: "UserContextThreads | None",
) -> MaintenanceProgress:
    """撤销后的维护进度：只失效真正受影响的上下文窗口。

    某上下文的有效切点（自身窗口或迁移冻结切点）之前有被删的本上下文消息、
    或被删消息属于它的工作摘要来源时，该窗口与摘要失效；其他窗口与迁移冻结
    切点保持，只随删除平移下标。代次照常推进，让撤销前准备的窗口与回合草稿
    全部过期。
    """
    deleted_ids = {str(messages[index]["id"]) for index in indices}

    def owns(key: str, message: dict[str, Any]) -> bool:
        return key == "session" or message_window_key(message, user_threads) == key

    # Contexts relying only on a legacy cut have no window entry yet.
    keys = set(progress.windows) | {
        message_window_key(messages[index], user_threads) for index in indices
    }
    affected = {
        key
        for key in keys
        if any(
            index < progress.cut(key) and owns(key, messages[index])
            for index in indices
        )
        or deleted_ids & set(progress.summary_source_ids.get(key, []))
    }
    kept = progress.without_windows(affected).invalidated(keep_windows=True)
    return replace(
        kept,
        legacy_cuts={k: _shifted(c, indices) for k, c in kept.legacy_cuts.items()},
        windows={k: _shifted(c, indices) for k, c in kept.windows.items()},
    )


def _rolled_back_context_cursors(
    user_threads: "UserContextThreads",
    messages: list[dict[str, Any]],
    *,
    indices: list[int],
    old_cursors: dict[ContextScope, int],
    rollback_source_ids: list[str],
) -> dict[ContextScope, int]:
    """角色会话撤销后各上下文的游标。

    删除的消息与记忆来源都按此刻的身份绑定归入上下文，与整理时的划分一致；
    计算某类游标时只看这类上下文的删除与来源，另一类的来源不会把它多拉回。
    """
    from conversation.context_scope import role_context_views

    by_id = {str(message.get("id") or ""): message for message in messages}
    cursors: dict[ContextScope, int] = {}
    for view in role_context_views(user_threads):
        cursors[view.scope] = _rolled_back_cursor(
            messages,
            indices=indices,
            scoped_indices=[
                index for index in indices if view.includes(messages[index])
            ],
            old_cursor=old_cursors[view.scope],
            rollback_source_ids=[
                source_id
                for source_id in (str(item).strip() for item in rollback_source_ids)
                if source_id in by_id and view.includes(by_id[source_id])
            ],
        )
    return cursors


def _rolled_back_cursor(
    messages: list[dict[str, Any]],
    *,
    indices: list[int],
    scoped_indices: list[int],
    old_cursor: int,
    rollback_source_ids: list[str],
) -> int:
    """一个整理游标在删除 ``indices`` 后的新值。

    只有 ``scoped_indices``（删除的消息里属于这个游标那类上下文的）落在游标之前时，
    游标才退回重新整理；其余删除只让游标随之平移。
    """
    rollback_index = _compute_rollback_index(
        messages,
        delete_indices=scoped_indices,
        old_last_consolidated=old_cursor,
        rollback_source_ids=rollback_source_ids,
    )
    return max(0, min(_shifted(rollback_index, indices), len(messages) - len(indices)))
