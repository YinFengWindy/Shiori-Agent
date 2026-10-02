"""Public value result for an atomic session undo."""

from dataclasses import dataclass
from collections.abc import Callable
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class UndoSessionResult:
    """Persisted message identities and consolidation cursor affected by undo."""

    deleted_ids: list[str]
    target_user_id: str
    target_assistant_id: str
    rollback_index: int
    last_consolidated_before: int
    last_consolidated_after: int


class SessionUndo(Protocol):
    """Atomically remove one passive turn after resolving its memory source IDs."""

    async def undo_last_turn(
        self,
        session_key: str,
        *,
        rollback_source_resolver: Callable[[list[str]], list[str]] | None = None,
    ) -> UndoSessionResult | None: ...


@runtime_checkable
class MemoryUndo(Protocol):
    """Preview or apply memory mutations associated with deleted message IDs."""

    def undo_by_message_sources(
        self, message_ids: list[str], *, dry_run: bool = False
    ) -> dict[str, object]: ...


class SessionView(Protocol):
    """Read-only metadata needed by role-based plugin events."""

    @property
    def metadata(self) -> dict[str, object]: ...


class PluginSessions(Protocol):
    """Metadata, original media and atomic replacement with host-owned presentation."""

    def get_or_create(self, key: str) -> SessionView: ...
    def role_session_key(self, role_id: str) -> str: ...
    def original_media_path(self, value: str) -> str: ...
    def get_message_media(
        self, *, session_key: str, message_id: str, media_index: int
    ) -> str: ...
    async def replace_message_media(
        self,
        *,
        session_key: str,
        message_id: str,
        media_index: int,
        expected_path: str,
        new_path: str,
    ) -> dict[str, object]: ...
