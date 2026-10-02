"""Prepare and commit independent model windows under session ownership."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from session.maintenance_progress import (
    MaintenanceProgress,
    ownership_key,
    window_key,
    message_prefix_stamp,
)

from session.turns import retention_stop
from .manager import _ManagerCoreMixin
from .models import Session, consolidation_cursor

if TYPE_CHECKING:
    from conversation.context_scope import ContextView


@dataclass(frozen=True)
class WindowPreparation:
    """Immutable message range and ownership/version preconditions for compaction."""

    session_key: str
    view: ContextView | None
    expected_message_ids: tuple[str, ...]
    removed_message_ids: tuple[str, ...]
    ownership: str
    generation: int
    version: int
    start: int
    stop: int
    prefix_stamp: str
    retained_turns: int = 0
    request_owner: str = ""


class _WindowMixin(_ManagerCoreMixin):
    async def bind_window_request(
        self, session_key: str, view: ContextView | None, owner: str
    ) -> None:
        """Invalidate a derived window when its actual connection/model changes."""
        async with self._lock(session_key):
            session = self.get_or_create(session_key)
            progress = self.maintenance_progress(session, allow_invalidation=True)
            if progress.ownership != ownership_key(view.user_threads if view else None):
                raise ValueError("上下文身份归属已变化，请重新准备回合")
            key = window_key(view)
            previous = progress.request_owners.get(key)
            if previous == owner:
                return
            next_progress = MaintenanceProgress.load(progress.dump())
            if previous is not None:
                next_progress.windows[key] = 0
                next_progress.summaries.pop(key, None)
                next_progress.summary_source_ids.pop(key, None)
                next_progress.window_versions[key] = (
                    progress.window_versions.get(key, 0) + 1
                )
            next_progress.request_owners[key] = owner
            self._store.write_maintenance_progress(session.key, next_progress.dump())
            session.maintenance_progress = next_progress

    def window_snapshot(
        self,
        session_key: str,
        view: ContextView | None,
        *,
        message_limit: int,
        expected: MaintenanceProgress | None = None,
    ) -> Session:
        """Read committed state without importing messages after this execution began.

        A retry can observe a newer cut/summary, but must retain the original
        identity, model owner and generation. Undo or a changed binding requires
        a new execution instead of sending a request under its old ContextView.
        """
        session = self.get_or_create(session_key)
        progress = self.maintenance_progress(session, allow_invalidation=True)
        key = window_key(view)
        if expected is not None and (
            progress.ownership != expected.ownership
            or progress.generation != expected.generation
            or progress.request_owners.get(key, "")
            != expected.request_owners.get(key, "")
            or progress.ownership != ownership_key(view.user_threads if view else None)
            or progress.cursor(view) > message_limit
        ):
            raise ValueError("上下文窗口归属或代次已变化，请重新准备回合")
        return replace(
            session,
            messages=session.messages[:message_limit],
            maintenance_progress=progress,
        )

    async def prepare_window(
        self,
        session_key: str,
        view: ContextView | None,
        *,
        keep_turns: int,
        message_limit: int | None = None,
    ) -> WindowPreparation | None:
        """Freeze a complete-turn prefix without touching memory or current requests."""
        if type(keep_turns) is not int or keep_turns < 0:
            raise ValueError("保留轮数必须是非负整数")
        async with self._lock(session_key):
            session = self.get_or_create(session_key)
            progress = self.maintenance_progress(session, allow_invalidation=True)
            if progress.ownership != ownership_key(view.user_threads if view else None):
                raise ValueError("上下文身份归属已变化，请重新准备回合")
            key = window_key(view)
            start = progress.cursor(view)
            members = [
                index
                for index, message in enumerate(session.messages)
                if (message_limit is None or index < message_limit)
                and (view is None or view.includes(message))
            ]
            if not members:
                return None
            bounded_messages = session.messages[:message_limit]
            stop, retained = retention_stop(bounded_messages, members, keep_turns)
            removed = tuple(
                str(session.messages[index].get("id") or "")
                for index in members
                if start <= index < stop
            )
            ids = tuple(str(message.get("id") or "") for message in session.messages)
            if not removed or not all(ids):
                return None
            return WindowPreparation(
                session_key,
                view,
                ids,
                removed,
                progress.ownership,
                progress.generation,
                progress.window_versions.get(key, 0),
                start,
                stop,
                message_prefix_stamp(session.messages),
                retained,
                progress.request_owners.get(key, ""),
            )

    async def commit_window(
        self, prepared: WindowPreparation, summary: str, source_ids: tuple[str, ...]
    ) -> bool:
        """Publish the summary and window together after their memory prerequisite.

        Appends are allowed, but never included in the prepared cut. A changed
        identity, prefix, generation or window version invalidates the draft.
        """
        async with self._lock(prepared.session_key):
            session = self.get_or_create(prepared.session_key)
            progress = self.maintenance_progress(session, allow_invalidation=True)
            key = window_key(prepared.view)
            messages = self._store.fetch_session_messages(prepared.session_key)
            if (
                not summary.strip()
                or not source_ids
                or not set(source_ids).issubset(
                    set(prepared.removed_message_ids)
                    | set(progress.summary_source_ids.get(key, []))
                )
                or progress.request_owners.get(key, "") != prepared.request_owner
                or progress.ownership != prepared.ownership
                or progress.generation != prepared.generation
                or progress.window_versions.get(key, 0) != prepared.version
                or progress.cursor(prepared.view) != prepared.start
                or tuple(
                    str(m["id"]) for m in messages[: len(prepared.expected_message_ids)]
                )
                != prepared.expected_message_ids
                or message_prefix_stamp(messages[: len(prepared.expected_message_ids)])
                != prepared.prefix_stamp
                or not 0
                <= prepared.start
                < prepared.stop
                <= len(prepared.expected_message_ids)
            ):
                return False
            scope = prepared.view.scope if prepared.view else None
            memory_cursor = consolidation_cursor(session, scope)
            # Compare actual members of the removed range against the category
            # cursor; never compare the external-thread cut as if it were a scope.
            if any(
                index >= memory_cursor
                and str(message["id"]) in prepared.removed_message_ids
                for index, message in enumerate(messages)
            ):
                return False
            if progress.consumer_error or progress.pending_consumers:
                return False
            next_progress = MaintenanceProgress.load(progress.dump())
            next_progress.windows[key] = prepared.stop
            next_progress.summaries[key] = summary
            next_progress.summary_source_ids[key] = list(source_ids)
            next_progress.window_versions[key] = prepared.version + 1
            self._store.write_maintenance_progress(session.key, next_progress.dump())
            session.maintenance_progress = next_progress
            return True
