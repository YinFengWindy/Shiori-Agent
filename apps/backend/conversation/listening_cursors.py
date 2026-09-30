"""每群旁听记录的整理游标（#541）。

游标是该群旁听记录里已整理到的 ``seq``（含），没有记录时为 0。它与角色会话的
整理游标（``sessions`` 表里的按上下文游标）完全分开：旁听整理只推进这里。
"""

from __future__ import annotations

import sqlite3
import threading

from infra.persistence.sqlite_transaction import immediate_transaction


class ListeningCursors:
    """Each group's listening consolidation cursor in ``listening_cursors``.

    Shares ``sessions.db``'s connection and lock with the conversation store.
    """

    def __init__(
        self, connection: sqlite3.Connection, lock: threading.Lock | threading.RLock
    ) -> None:
        self._conn = connection
        self._lock = lock

    def get(self, thread_id: str) -> int:
        """The last consolidated ``seq`` of the group's records; 0 before any."""
        with self._lock:
            return self._get(thread_id)

    def advance(self, thread_id: str, *, expected: int, to: int) -> bool:
        """Moves the group's cursor from ``expected`` to ``to``.

        False, changing nothing, when the cursor is no longer ``expected``
        (another consolidation of the group committed first). The cursor only
        moves forward.
        """
        if to <= expected:
            raise ValueError("旁听整理游标只能前进")
        with self._lock:
            with immediate_transaction(self._conn):
                if self._get(thread_id) != expected:
                    return False
                _ = self._conn.execute(
                    """
                    INSERT INTO listening_cursors (thread_id, consolidated_seq)
                    VALUES (?, ?)
                    ON CONFLICT(thread_id) DO UPDATE
                    SET consolidated_seq = excluded.consolidated_seq
                    """,
                    (thread_id, to),
                )
        return True

    def _get(self, thread_id: str) -> int:
        """The cursor; the caller holds the lock."""
        row = self._conn.execute(
            "SELECT consolidated_seq FROM listening_cursors WHERE thread_id = ?",
            (thread_id,),
        ).fetchone()
        return int(row[0]) if row is not None else 0
