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
