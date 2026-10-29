"""Session presence over the existing heartbeat columns (D19).

The table columns stay ``last_user_at`` and ``last_proactive_at``.
``record_initiated_sent`` writes ``last_proactive_at``. ``proactive_v2`` keeps
its own store until initiated delivery moves; this object is what
``SessionManager.presence`` exposes to plugins.
"""

from __future__ import annotations

from datetime import datetime

from core.common.timekit import format_iso, parse_iso
from session.store import SessionStore


class SessionPresence:
    """Map the sessions socket onto one session store."""

    def __init__(self, store: SessionStore) -> None:
        self._store = store

    def record_user_message(self, session_key: str, when: datetime) -> None:
        """Record that the user spoke in ``session_key`` at ``when``."""
        self._store.update_presence(
            self._store.presence_key(session_key), last_user_at=format_iso(when)
        )

    def last_user_at(self, session_key: str) -> datetime | None:
        """When the user last spoke, or None if this session has no record."""
        return self._read(session_key, "last_user_at")

    def record_initiated_sent(self, session_key: str, when: datetime) -> None:
        """Record that an initiated reply was sent for ``session_key`` at ``when``."""
        self._store.update_presence(
            self._store.presence_key(session_key), last_proactive_at=format_iso(when)
        )

    def last_initiated_at(self, session_key: str) -> datetime | None:
        """When an initiated reply was last sent, or None."""
        return self._read(session_key, "last_proactive_at")

    def _read(self, session_key: str, column: str) -> datetime | None:
        row = self._store.get_presence(self._store.presence_key(session_key))
        return None if row is None else parse_iso(row[column])
