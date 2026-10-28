"""Session presence over the existing heartbeat columns (D19).

The table columns stay ``last_user_at`` and ``last_proactive_at``.
``record_initiated_sent`` writes ``last_proactive_at``. ``proactive_v2`` keeps
its own store until initiated delivery moves; this object is what
``SessionManager.presence`` exposes to plugins.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from core.common.timekit import format_iso, parse_iso


class SessionPresence:
    """Map the sessions socket onto one session store."""

    def __init__(self, store: Any) -> None:
        self._store = store

    def record_user_message(self, session_key: str, when: datetime) -> None:
        """Record that the user spoke in ``session_key`` at ``when``."""
        self._store.update_presence(
            self._role_key(session_key), last_user_at=format_iso(when)
        )

    def last_user_at(self, session_key: str) -> datetime | None:
        """When the user last spoke, or None if this session has no record."""
        return self._read(session_key, "last_user_at")

    def record_initiated_sent(self, session_key: str, when: datetime) -> None:
        """Record that an initiated reply was sent for ``session_key`` at ``when``."""
        self._store.update_presence(
            self._role_key(session_key), last_proactive_at=format_iso(when)
        )

    def last_initiated_at(self, session_key: str) -> datetime | None:
        """When an initiated reply was last sent, or None."""
        return self._read(session_key, "last_proactive_at")

    def _read(self, session_key: str, column: str) -> datetime | None:
        row = self._store.get_presence(self._role_key(session_key)) or {}
        return parse_iso(row.get(column))

    def _role_key(self, session_key: str) -> str:
        clean_key = str(session_key or "").strip()
        if not clean_key or clean_key.startswith("role:"):
            return clean_key
        meta = self._store.get_session_meta(clean_key) or {}
        metadata = meta.get("metadata") if isinstance(meta, dict) else {}
        if isinstance(metadata, dict):
            role_id = str(metadata.get("role_id") or "").strip()
            if role_id:
                return f"role:{role_id}"
        return clean_key
