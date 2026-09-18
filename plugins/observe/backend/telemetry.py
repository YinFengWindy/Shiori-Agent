"""Public, read-only telemetry queries owned by observe."""

from __future__ import annotations

import sqlite3
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class KVCacheTurn:
    """One agent reply's cache counters; None means the count was not recorded."""

    reply: str
    timestamp: str
    prompt_tokens: int | None
    hit_tokens: int | None


class ObserveTelemetry:
    """Expose immutable cache snapshots without giving consumers storage access."""

    def __init__(self, workspace: Path) -> None:
        from .storage import database_path

        self._db_path = database_path(workspace)

    def recent_cache_turns(
        self, session_key: str, *, limit: int = 5
    ) -> tuple[KVCacheTurn, ...]:
        """Return the latest 1–30 agent turns, newest first, for one session.

        Missing storage or no matching turns yields an empty tuple. Reads never
        create or migrate storage. Storage query failures propagate as OSError,
        with the SQLite exception preserved as the cause.
        """
        if not self._db_path.is_file():
            return ()
        try:
            uri = self._db_path.resolve().as_uri() + "?mode=ro"
            with closing(sqlite3.connect(uri, uri=True)) as connection:
                rows = connection.execute(
                    """SELECT llm_output, ts,
                              react_cache_prompt_tokens, react_cache_hit_tokens
                       FROM turns WHERE session_key=? AND source='agent'
                       ORDER BY id DESC LIMIT ?""",
                    (session_key, max(1, min(30, limit))),
                ).fetchall()
        except sqlite3.Error as exc:
            raise OSError("读取 KVCache 遥测失败") from exc
        return tuple(KVCacheTurn(*row) for row in rows)
