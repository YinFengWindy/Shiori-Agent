"""The ``sessions`` socket: roll back the latest passive turn (D10).

The core session module provides ``SESSIONS``. ``RollbackResult.turn_id`` is
the anchor user message id of that turn — the id memory ``source_ref`` values
use — not a desktop ``metadata.turn_id``.

``last_passive_turn_id`` reads that id without deleting, so memory can roll
back first. ``rollback_last_turn`` then deletes the turn.
``rollback_source_ids`` rewinds the consolidation cursor across the memory
window those sources cover. The two calls are not one transaction.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from shiori_sdk.kernel import Key


@dataclass(frozen=True)
class RollbackResult:
    """The passive turn a session rollback deleted, and where the cursor moved.

    ``turn_id`` is ``target_user_id``: the anchor user message of that turn.
    """

    turn_id: str
    deleted_ids: tuple[str, ...]
    target_user_id: str
    target_assistant_id: str
    rollback_index: int
    last_consolidated_before: int
    last_consolidated_after: int


class Sessions(Protocol):
    """Read or delete the latest committed passive turn of one session."""

    def last_passive_turn_id(self, session_key: str) -> str | None:
        """The anchor user message id of the latest passive turn, or None.

        Does not delete. A later ``rollback_last_turn`` selects again under
        the session write lock, so a turn that arrives in between can differ.
        """
        ...

    async def rollback_last_turn(
        self,
        session_key: str,
        *,
        rollback_source_ids: list[str] | None = None,
    ) -> RollbackResult | None:
        """Delete the latest passive turn, or None when there is nothing to undo.

        ``rollback_source_ids`` are message ids whose memories were already
        rolled back. They pull the consolidation cursor back to the start of
        that window. Omit them to rewind only for the deleted messages.
        """
        ...


SESSIONS: Key[Sessions] = Key("sessions")
"""Provided by the core session module; plugins declare it in ``inject``."""
