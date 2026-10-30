"""The ``sessions`` socket: roll back the latest passive turn, and presence (D10, D19).

The core session module provides ``SESSIONS``. A turn's ``turn_id`` is the
anchor user message id of that turn — the id memory ``source_ref`` values
use — not a desktop ``metadata.turn_id``.

``last_passive_turn`` reads the turn without deleting it, so memory can roll
back first over every message id of the turn. ``rollback_last_turn`` then
deletes it under the session write lock; ``expected_turn`` makes it refuse
when the latest turn is no longer exactly that turn (same anchor and same
message ids) by then. The two calls are not one
transaction.

This ``Key`` (name ``sessions``) is unrelated to session metadata and media.
That surface is ``SESSION_STORE`` (name ``session_store``) in
``shiori_sdk.core.services``. A plugin that rolls a turn back injects
``sessions``; one that reads metadata or media injects ``session_store``.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from shiori_sdk.kernel import Key


@dataclass(frozen=True)
class PassiveTurn:
    """The latest committed passive turn of one session, read before deleting.

    ``message_ids`` are every message the rollback would delete: context
    frames, the anchor user message, tool messages and the whole assistant
    reply sequence. ``turn_id`` is among them.
    """

    turn_id: str
    message_ids: tuple[str, ...]


@dataclass(frozen=True)
class RollbackResult:
    """The passive turn a session rollback deleted, and how the cursor moved."""

    turn_id: str
    deleted_ids: tuple[str, ...]
    last_consolidated_before: int
    last_consolidated_after: int


@dataclass(frozen=True)
class TurnChanged:
    """Nothing was deleted: the latest passive turn is not ``expected_turn``.

    ``turn_id`` is the anchor of the latest passive turn under the lock. It
    can equal the expected anchor when the turn's messages changed, such as a
    reply sequence that grew after ``last_passive_turn`` was read; otherwise a
    newer passive turn was committed in between.
    """

    turn_id: str


class Presence(Protocol):
    """User and initiated-send heartbeats, kept per session.

    The stored columns stay ``last_user_at`` and ``last_proactive_at``.
    ``record_initiated_sent`` writes ``last_proactive_at``. A ``role:`` key is
    used as-is; any other key follows ``metadata.role_id`` when that session
    has one. This is the 4.0 baseline. 4.x cannot add methods here later.
    """

    def record_user_message(self, session_key: str, when: datetime) -> None:
        """Record that the user spoke in ``session_key`` at ``when``."""
        ...

    def last_user_at(self, session_key: str) -> datetime | None:
        """When the user last spoke, or None if this session has no record."""
        ...

    def record_initiated_sent(self, session_key: str, when: datetime) -> None:
        """Record that an initiated reply was sent for ``session_key`` at ``when``."""
        ...

    def last_initiated_at(self, session_key: str) -> datetime | None:
        """When an initiated reply was last sent, or None."""
        ...

    def most_recent_user_at(self) -> datetime | None:
        """When the user last spoke in any session, or None if never."""
        ...


class Sessions(Protocol):
    """Read or delete the latest committed passive turn of one session."""

    def last_passive_turn(self, session_key: str) -> PassiveTurn | None:
        """The latest passive turn, or None when there is nothing to undo.

        Does not delete and does not take the session write lock.
        """
        ...

    async def rollback_last_turn(
        self,
        session_key: str,
        *,
        expected_turn: PassiveTurn | None = None,
        rollback_source_ids: Sequence[str] = (),
    ) -> RollbackResult | TurnChanged | None:
        """Delete the latest passive turn, or None when there is nothing to undo.

        With ``expected_turn``, the turn is deleted only when both its anchor
        and its message ids equal it; otherwise nothing is deleted and
        ``TurnChanged`` is returned. ``rollback_source_ids`` are message
        ids whose memories were already rolled back; they pull the
        consolidation cursor back to the start of that window. Without them
        the cursor only rewinds for the deleted messages.
        """
        ...

    @property
    def presence(self) -> Presence:
        """Heartbeats for user messages and initiated sends (D19)."""
        ...


SESSIONS: Key[Sessions] = Key("sessions")
"""Provided by the core session module; plugins declare it in ``inject``."""
