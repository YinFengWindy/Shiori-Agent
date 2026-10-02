"""Maintenance state migration and identity normalization owned by SessionManager."""

from session.maintenance_progress import (
    MaintenanceProgress,
    legacy_progress,
    ownership_key,
)

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
            progress = self.maintenance_progress(session, persist=True)
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
        self, session: Session, *, persist: bool = False
    ) -> MaintenanceProgress:
        """Load progress, normalizing legacy state and identity ownership.

        Normalization is a pure function of the stored state and the current
        binding, so readers (status queries, window preparation) compute it in
        memory only. Write owners holding the session lock pass ``persist`` to
        store it before publishing their own change.
        """
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
        if progress.ownership != stamp:
            # Visibility changed: affected windows must not keep a cut or summary
            # built from messages they can no longer (or can now) see.
            progress = progress.rebound(stamp)
        if persist and raw != progress.dump():
            self._store.write_maintenance_progress(session.key, progress.dump())
        session.maintenance_progress = progress
        return progress
