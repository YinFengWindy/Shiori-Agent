"""Resume committed memory consumers without re-running memory extraction."""

from collections.abc import Awaitable, Callable
from typing import Any

from .manager import _ManagerCoreMixin
from session.maintenance_progress import MaintenanceProgress

# Consumer payload keys. A pending payload is the newest commit; ``backlog``
# holds only older commits whose event publication has not happened yet.
PUBLISHED = "published"
BACKLOG = "backlog"


class MemoryConsumersFailedError(RuntimeError):
    """Memory facts and cursor committed; an awaited downstream consumer failed."""


def unpublished_entries(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Commits still awaiting publication, oldest first, as live references."""
    return [
        entry
        for entry in (*payload.get(BACKLOG, ()), payload)
        if entry and not entry.get(PUBLISHED)
    ]


def publication_fields(entry: dict[str, Any]) -> dict[str, Any]:
    """The extracted commit itself, without consumer bookkeeping keys."""
    return {k: v for k, v in entry.items() if k not in (PUBLISHED, BACKLOG)}


def mark_published(payload: dict[str, Any], entry: dict[str, Any]) -> None:
    """Mark one commit published; published backlog entries carry no more work.

    Relationship refresh is session-wide, so the newest payload alone keeps the
    pending marker; this keeps the backlog bounded by unpublished commits.
    """
    entry[PUBLISHED] = True
    backlog = [item for item in payload.get(BACKLOG, ()) if not item.get(PUBLISHED)]
    if backlog:
        payload[BACKLOG] = backlog
    else:
        payload.pop(BACKLOG, None)


def carry_unpublished(previous: dict[str, Any], payload: dict[str, Any]) -> None:
    """Queue an earlier commit's unpublished work ahead of a new payload in place."""
    backlog = [publication_fields(entry) for entry in unpublished_entries(previous)]
    if backlog:
        payload[BACKLOG] = backlog


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
        progress.pending_consumers = payload
        # The caller marks each published entry; the newest is published last.
        if payload.get(PUBLISHED):
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
            progress = self.maintenance_progress(session, persist=True)
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
