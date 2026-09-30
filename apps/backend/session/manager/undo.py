"""Atomic passive-turn undo owned by the session manager."""

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from session.store.common import ContextScope

from .manager import _ManagerCoreMixin
from .models import effective_context_cursors
from .undo_result import UndoSessionResult
from .undo_selection import _compute_rollback_index, _find_last_passive_turn

if TYPE_CHECKING:
    from conversation.context_scope import UserContextThreads


class _UndoMixin(_ManagerCoreMixin):
    async def undo_last_turn(
        self,
        session_key: str,
        *,
        rollback_source_resolver: Callable[[list[str]], list[str]] | None = None,
    ) -> UndoSessionResult | None:
        """Delete the latest committed passive turn under the session write lock.

        The synchronous resolver previews memory rollback sources while the selected
        message IDs are stable. Its failure leaves the session untouched. Pending
        message objects stay attached to the cached session for queued appends.
        """
        async with self._lock(session_key):
            messages = self._store.fetch_session_messages(session_key)
            target = _find_last_passive_turn(messages)
            if target is None:
                return None
            indices, user_index, assistant_index = target
            deleted_ids = [str(messages[index]["id"]) for index in indices]
            sources = (
                rollback_source_resolver(list(deleted_ids))
                if rollback_source_resolver is not None
                else []
            )
            meta = self._store.get_session_meta(session_key)
            old_last = max(0, int(meta["last_consolidated"])) if meta else 0
            context_cursors: dict[ContextScope, int] | None = None
            # 延迟导入：context_scope 依赖 session.manager，模块级导入会形成循环。
            from conversation.context_scope import role_session_user_threads

            user_threads = role_session_user_threads(self.workspace, session_key)
            if user_threads is not None:
                # 角色会话按上下文各自回退：删掉的消息只让它所属那类上下文的游标
                # 退回重新整理，另一类游标只随删除平移（#523）。
                rollback_index, context_cursors = _rolled_back_context_cursors(
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
                rollback_index, new_last = _rolled_back_cursor(
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

            def refresh_projections() -> None:
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
            return UndoSessionResult(
                deleted_ids=deleted_ids,
                target_user_id=str(messages[user_index]["id"]),
                target_assistant_id=str(messages[assistant_index]["id"]),
                rollback_index=rollback_index,
                last_consolidated_before=old_last,
                last_consolidated_after=new_last,
            )


def _rolled_back_context_cursors(
    user_threads: "UserContextThreads",
    messages: list[dict[str, Any]],
    *,
    indices: list[int],
    old_cursors: dict[ContextScope, int],
    rollback_source_ids: list[str],
) -> tuple[int, dict[ContextScope, int]]:
    """角色会话撤销后各上下文的游标，以及最靠前的回退位置。

    删除的消息与记忆来源都按此刻的身份绑定归入上下文，与整理时的划分一致；
    计算某类游标时只看这类上下文的删除与来源，另一类的来源不会把它多拉回。
    """
    from conversation.context_scope import role_context_views

    by_id = {str(message.get("id") or ""): message for message in messages}
    rollback_indices: list[int] = []
    cursors: dict[ContextScope, int] = {}
    for view in role_context_views(user_threads):
        rollback_index, cursors[view.scope] = _rolled_back_cursor(
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
        rollback_indices.append(rollback_index)
    return min(rollback_indices), cursors


def _rolled_back_cursor(
    messages: list[dict[str, Any]],
    *,
    indices: list[int],
    scoped_indices: list[int],
    old_cursor: int,
    rollback_source_ids: list[str],
) -> tuple[int, int]:
    """一个整理游标在删除 ``indices`` 后的回退位置与新值。

    只有 ``scoped_indices``（删除的消息里属于这个游标那类上下文的）落在游标之前时，
    游标才退回重新整理；其余删除只让游标随之平移。
    """
    rollback_index = _compute_rollback_index(
        messages,
        delete_indices=scoped_indices,
        old_last_consolidated=old_cursor,
        rollback_source_ids=rollback_source_ids,
    )
    return rollback_index, max(
        0,
        min(
            rollback_index - sum(index < rollback_index for index in indices),
            len(messages) - len(indices),
        ),
    )
