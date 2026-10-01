"""Resume committed memory consumers without re-running memory extraction."""

from collections.abc import Awaitable, Callable
from typing import Any

from .manager import _ManagerCoreMixin
from session.maintenance_progress import MaintenanceProgress


class MemoryConsumersFailedError(RuntimeError):
    """Memory facts and cursor committed; an awaited downstream consumer failed."""


class _MemoryConsumersMixin(_ManagerCoreMixin):
    def record_memory_publication(
        self, session_key: str, payload: dict[str, Any]
    ) -> None:
        """Checkpoint event publication inside a locked consumer callback.

        Relationship retry must not publish the successful memory2 input again.
        The payload object also belongs to the in-flight commit's progress.
        """
        meta = self._store.get_session_meta(session_key)
        if meta is None or not meta.get("maintenance_progress"):
            raise RuntimeError("memory publication has no committed progress")
        progress = MaintenanceProgress.load(meta["maintenance_progress"])
        payload["published"] = True
        progress.pending_consumers = payload
        progress.published_version = progress.memory_version
        self._store.write_maintenance_progress(session_key, progress.dump())

    async def retry_memory_consumers(
        self,
        session_key: str,
        consume: Callable[[dict[str, Any]], Awaitable[None]],
    ) -> None:
        """Retry the saved consumer payload under the same cancellation boundary."""
        from .consolidation import _finish_shielded

        async with self._lock(session_key):
            session = self.get_or_create(session_key)
            progress = self.maintenance_progress(session, allow_invalidation=True)
            if not progress.pending_consumers:
                return

            await _finish_shielded(
                self._complete_memory_consumers(
                    session_key,
                    progress,
                    lambda: consume(progress.pending_consumers),
                )
            )

    async def _complete_memory_consumers(
        self,
        session_key: str,
        progress: MaintenanceProgress,
        consume: Callable[[], Awaitable[None]] | None,
    ) -> None:
        """Finish or checkpoint consumers after the durable memory commit exists."""
        try:
            if consume is not None:
                await consume()
            completed = MaintenanceProgress.load(progress.dump())
            completed.pending_consumers = {}
            completed.consumer_error = ""
            completed.published_version = completed.memory_version
            completed.relationship_version = completed.memory_version
            self._store.write_maintenance_progress(session_key, completed.dump())
        except Exception as exc:
            if progress.pending_consumers.get("published"):
                progress.published_version = progress.memory_version
            progress.consumer_error = str(exc)
            session = self._cache.get(session_key)
            if session is not None:
                session.maintenance_progress = progress
            try:
                self._store.write_maintenance_progress(session_key, progress.dump())
            except Exception as checkpoint_error:
                raise MemoryConsumersFailedError(
                    f"{exc}; consumer checkpoint failed: {checkpoint_error}"
                ) from checkpoint_error
            raise MemoryConsumersFailedError(str(exc)) from exc
        session = self._cache.get(session_key)
        if session is not None:
            session.maintenance_progress = completed
