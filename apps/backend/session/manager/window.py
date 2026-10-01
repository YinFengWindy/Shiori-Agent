"""Prepare and commit independent model windows under session ownership."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from session.maintenance_progress import (
    MaintenanceProgress,
    ownership_key,
    window_key,
    message_prefix_stamp,
)

from .helpers import starts_turn
from .manager import _ManagerCoreMixin
from .models import consolidation_cursor

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


class _WindowMixin(_ManagerCoreMixin):
    async def prepare_window(
        self,
        session_key: str,
        view: ContextView | None,
        *,
        keep_count: int,
        force: bool = False,
    ) -> WindowPreparation | None:
        """Select the existing raw-history policy without touching memory progress."""
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
                if view is None or view.includes(message)
            ]
            if not members:
                return None
            stop = len(session.messages)
            if not force and 0 < keep_count < len(members):
                retained = len(members) - keep_count
                # Preserve the turn enclosing the first retained raw message.
                while retained > 0 and not starts_turn(
                    session.messages[members[retained]]
                ):
                    retained -= 1
                stop = members[retained]
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
            )

    async def commit_window(self, prepared: WindowPreparation) -> bool:
        """Publish only the prepared window after its scoped memory prerequisite.

        Appends are allowed, but never included in the prepared cut. A changed
        identity, prefix, generation or window version invalidates the draft.
        """
        async with self._lock(prepared.session_key):
            session = self.get_or_create(prepared.session_key)
            progress = self.maintenance_progress(session, allow_invalidation=True)
            key = window_key(prepared.view)
            messages = self._store.fetch_session_messages(prepared.session_key)
            if (
                progress.ownership != prepared.ownership
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
            next_progress.window_versions[key] = prepared.version + 1
            self._store.write_maintenance_progress(session.key, next_progress.dump())
            session.maintenance_progress = next_progress
            return True
