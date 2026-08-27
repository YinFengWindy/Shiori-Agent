"""Workspace catalog for Story databases and library lifecycle."""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import Any

from .errors import StoryNotFoundError
from .models import utc_now


_SCHEMA = """
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS story_entries (
    story_id TEXT PRIMARY KEY,
    relative_db_path TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS catalog_idempotency (
    request_id TEXT PRIMARY KEY,
    story_id TEXT NOT NULL REFERENCES story_entries(story_id)
);

CREATE TABLE IF NOT EXISTS catalog_request_payloads (
    request_id TEXT PRIMARY KEY,
    story_id TEXT NOT NULL REFERENCES story_entries(story_id),
    payload_hash TEXT NOT NULL
);
"""


class StoryCatalog:
    """Own library discovery metadata without owning Story facts."""

    def __init__(self, workspace: Path) -> None:
        self.root = workspace / "stories"
        self.root.mkdir(parents=True, exist_ok=True)
        self.db_path = self.root / "catalog.db"
        self._connection = sqlite3.connect(
            str(self.db_path), check_same_thread=False, isolation_level=None
        )
        self._connection.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        with self._lock:
            self._connection.executescript(_SCHEMA)

    def close(self) -> None:
        """Close the catalog connection."""

        with self._lock:
            self._connection.close()

    def create_entry(
        self, *, story_id: str, title: str, request_id: str, payload_hash: str
    ) -> dict[str, Any]:
        """Register one provisioning Story idempotently before its database is opened."""

        clean_title = title.strip()
        if not clean_title:
            raise ValueError("title 不能为空")
        relative_db_path = (Path(story_id) / "story.db").as_posix()
        with self._transaction() as connection:
            existing = connection.execute(
                """SELECT catalog_idempotency.story_id, catalog_request_payloads.payload_hash
                FROM catalog_idempotency
                JOIN catalog_request_payloads USING (request_id)
                WHERE request_id = ?""",
                (request_id,),
            ).fetchone()
            if existing is not None:
                if existing["story_id"] != story_id:
                    raise ValueError("request_id 已用于另一个 Story")
                if existing["payload_hash"] != payload_hash:
                    raise ValueError("request_id 携带了不同的请求")
            else:
                connection.execute(
                    "INSERT INTO story_entries VALUES (?, ?, ?, 'provisioning', ?)",
                    (story_id, relative_db_path, clean_title, utc_now()),
                )
                connection.execute(
                    "INSERT INTO catalog_idempotency VALUES (?, ?)",
                    (request_id, story_id),
                )
                connection.execute(
                    "INSERT INTO catalog_request_payloads VALUES (?, ?, ?)",
                    (request_id, story_id, payload_hash),
                )
        return self.require_entry(story_id)

    def require_entry(self, story_id: str) -> dict[str, Any]:
        """Return one catalog entry or a stable Story error."""

        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM story_entries WHERE story_id = ?", (story_id,)
            ).fetchone()
        if row is None:
            raise StoryNotFoundError(f"story not found: {story_id}")
        return dict(row)

    def story_id_for_request(
        self, request_id: str, *, payload_hash: str
    ) -> str | None:
        """Resolve a previous create request without generating a second Story."""

        with self._lock:
            row = self._connection.execute(
                """SELECT catalog_idempotency.story_id, catalog_request_payloads.payload_hash
                FROM catalog_idempotency
                JOIN catalog_request_payloads USING (request_id)
                WHERE request_id = ?""",
                (request_id,),
            ).fetchone()
        if row is None:
            return None
        if row["payload_hash"] != payload_hash:
            raise ValueError("request_id 携带了不同的请求")
        return str(row["story_id"])

    def request_id_for_story(self, story_id: str) -> str | None:
        """Return the logical creation key associated with one Story."""

        with self._lock:
            row = self._connection.execute(
                "SELECT request_id FROM catalog_idempotency WHERE story_id = ?",
                (story_id,),
            ).fetchone()
        return None if row is None else str(row["request_id"])

    def list_entries(self) -> list[dict[str, Any]]:
        """Return all catalog entries for startup recovery."""

        with self._lock:
            rows = self._connection.execute(
                "SELECT * FROM story_entries ORDER BY created_at, story_id"
            ).fetchall()
        return [dict(row) for row in rows]

    def list_summaries(self, *, include_archived: bool = False) -> list[dict[str, Any]]:
        """List active Stories by default, with an explicit archived opt-in."""

        query = "SELECT * FROM story_entries"
        params: tuple[Any, ...] = ()
        query += " WHERE status IN ('active', 'archived')" if include_archived else " WHERE status = 'active'"
        query += " ORDER BY created_at, story_id"
        with self._lock:
            rows = self._connection.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def set_status(self, story_id: str, status: str) -> dict[str, Any]:
        """Update a library status without touching Story facts."""

        if status not in {"provisioning", "active", "archived", "deleting"}:
            raise ValueError("invalid Story catalog status")
        with self._lock:
            updated = self._connection.execute(
                "UPDATE story_entries SET status = ? WHERE story_id = ?",
                (status, story_id),
            )
        if updated.rowcount != 1:
            raise StoryNotFoundError(f"story not found: {story_id}")
        return self.require_entry(story_id)

    def delete_entry(self, story_id: str) -> None:
        """Remove one catalog entry after its private database is removed."""

        with self._transaction() as connection:
            connection.execute(
                "DELETE FROM catalog_request_payloads WHERE story_id = ?", (story_id,)
            )
            connection.execute(
                "DELETE FROM catalog_idempotency WHERE story_id = ?", (story_id,)
            )
            connection.execute("DELETE FROM story_entries WHERE story_id = ?", (story_id,))

    def database_path(self, story_id: str) -> Path:
        """Resolve a registered Story database below the catalog root."""

        entry = self.require_entry(story_id)
        candidate = (self.root / entry["relative_db_path"]).resolve()
        root = self.root.resolve()
        if candidate == root or root not in candidate.parents:
            raise ValueError("Story database path escapes workspace")
        return candidate

    def _transaction(self):
        class _Transaction:
            def __init__(self, owner: StoryCatalog) -> None:
                self.owner = owner

            def __enter__(self):
                self.owner._lock.acquire()
                self.owner._connection.execute("BEGIN IMMEDIATE")
                return self.owner._connection

            def __exit__(self, exc_type, exc, traceback):
                if exc_type is None:
                    self.owner._connection.commit()
                else:
                    self.owner._connection.rollback()
                self.owner._lock.release()
                return False

        return _Transaction(self)
