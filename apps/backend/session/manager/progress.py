"""Maintenance state migration and invalidation owned by SessionManager."""

from session.maintenance_progress import (
    MaintenanceProgress,
    legacy_progress,
    ownership_key,
)

from session.store.common import ContextScope
from .manager import _ManagerCoreMixin
from .models import Session


class _ProgressMixin(_ManagerCoreMixin):
    async def record_recent_context(
        self,
        session_key: str,
        source_ids: tuple[str, ...],
        ownership: str,
    ) -> None:
        """Stamp a recent-turn refresh separately from memory and relationships."""
        async with self._lock(session_key):
            session = self.get_or_create(session_key)
            progress = self.maintenance_progress(session, allow_invalidation=True)
            current_ids = tuple(str(m.get("id") or "") for m in session.messages)
            if (
                progress.ownership != ownership
                or current_ids[: len(source_ids)] != source_ids
            ):
                return
            updated = MaintenanceProgress.load(progress.dump())
            updated.recent_context_version += 1
            updated.recent_context_source_ids = list(source_ids)
            self._store.write_maintenance_progress(session_key, updated.dump())
            session.maintenance_progress = updated

    def maintenance_progress(
        self, session: Session, *, allow_invalidation: bool = False
    ) -> MaintenanceProgress:
        """Load or migrate progress, invalidating stale identity ownership first."""
        from conversation.context_scope import role_session_user_threads

        # Projection callbacks can read a cached session inside an owning SQL
        # transaction. Never publish its uncommitted cursor/state into that cache.
        if (
            self._store._conn.in_transaction
            and session.maintenance_progress is not None
        ):
            return session.maintenance_progress
        stamp = ownership_key(role_session_user_threads(self.workspace, session.key))
        meta = self._store.get_session_meta(session.key)
        if meta is not None:
            session.last_consolidated = meta["last_consolidated"]
            session.context_cursors = meta["context_cursors"]
        raw = meta.get("maintenance_progress") if meta else None
        progress = (
            MaintenanceProgress.load(raw) if raw else legacy_progress(session, stamp)
        )
        if progress.ownership != stamp and (
            allow_invalidation or not self._lock(session.key).locked()
        ):
            # Visibility changed: replay only currently permitted messages. Old
            # windows and consumer snapshots must never establish a new cut.
            progress = progress.invalidated(ownership=stamp)
            cursors: dict[ContextScope, int] | None = (
                {"user": 0, "external": 0} if stamp else None
            )
            with self._store.transaction():
                self._store.update_last_consolidated(
                    session.key, 0, context_cursors=cursors, commit=False
                )
                self._store.write_maintenance_progress(
                    session.key, progress.dump(), commit=False
                )
            session.set_consolidation_cursors(0, cursors)
        if raw != progress.dump():
            self._store.write_maintenance_progress(session.key, progress.dump())
        session.maintenance_progress = progress
        return progress

    async def invalidate_maintenance(self, session_key: str) -> None:
        """Invalidate derived maintenance without deleting any original message."""
        async with self._lock(session_key):
            session = self.get_or_create(session_key)
            old = self.maintenance_progress(session)
            progress = old.invalidated()
            cursors: dict[ContextScope, int] | None = (
                {"user": 0, "external": 0} if old.ownership else None
            )
            with self._store.transaction():
                self._store.write_maintenance_progress(
                    session_key, progress.dump(), commit=False
                )
                self._store.update_last_consolidated(
                    session_key, 0, context_cursors=cursors, commit=False
                )
            session.maintenance_progress = progress
            session.set_consolidation_cursors(0, cursors)
