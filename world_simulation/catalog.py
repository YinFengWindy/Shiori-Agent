"""Workspace catalog for world drafts, database locations, and list summaries."""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import Any

from world_simulation.errors import WorldNotFoundError
from world_simulation.repository_records import _dump, _load
from world_simulation.world import (
    NativeResident,
    RoleTemplateSnapshot,
    WorldDraft,
    WorldTemplate,
    utc_now,
)


_CATALOG_SCHEMA = """
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS world_drafts (
    id TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL,
    payload TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS world_entries (
    world_id TEXT PRIMARY KEY,
    relative_db_path TEXT NOT NULL UNIQUE,
    summary TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS catalog_idempotency (
    request_id TEXT PRIMARY KEY,
    world_id TEXT NOT NULL REFERENCES world_entries(world_id)
);

CREATE TABLE IF NOT EXISTS world_creation_intents (
    request_id TEXT PRIMARY KEY,
    world_id TEXT NOT NULL UNIQUE,
    draft_id TEXT,
    relative_db_path TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    completed_at TEXT
);
"""


class WorldCatalog:
    """Persist workspace-level discovery data without owning world facts."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(
            str(self.db_path), check_same_thread=False, isolation_level=None
        )
        self._connection.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        with self._lock:
            self._connection.executescript(_CATALOG_SCHEMA)

    def close(self) -> None:
        """Close the catalog connection."""

        with self._lock:
            self._connection.close()

    def save_draft(self, draft: WorldDraft) -> None:
        """Persist a newly previewed world draft."""

        with self._lock:
            self._connection.execute(
                "INSERT INTO world_drafts VALUES (?, ?, ?, ?, ?)",
                (
                    draft.id,
                    draft.owner_id,
                    _dump(self._draft_payload(draft)),
                    draft.status,
                    draft.created_at,
                ),
            )

    def get_draft(self, draft_id: str) -> WorldDraft | None:
        """Load a draft without opening any world database."""

        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM world_drafts WHERE id = ?", (draft_id,)
            ).fetchone()
        return self._row_to_draft(row) if row is not None else None

    def replace_draft(self, draft: WorldDraft) -> None:
        """Save player edits while the draft remains confirmable."""

        with self._lock:
            updated = self._connection.execute(
                """UPDATE world_drafts SET payload = ?
                WHERE id = ? AND status = 'draft'""",
                (_dump(self._draft_payload(draft)), draft.id),
            )
        if updated.rowcount != 1:
            raise WorldNotFoundError(f"world draft is not editable: {draft.id}")

    def register_creation_intent(
        self,
        *,
        request_id: str,
        world_id: str,
        draft_id: str | None,
        relative_db_path: str,
    ) -> dict[str, Any]:
        """Record a world creation before its dedicated database is opened."""

        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                row = self._connection.execute(
                    "SELECT * FROM world_creation_intents WHERE request_id = ?",
                    (request_id,),
                ).fetchone()
                if row is None:
                    self._connection.execute(
                        """INSERT INTO world_creation_intents
                        VALUES (?, ?, ?, ?, 'pending', ?, NULL)""",
                        (
                            request_id,
                            world_id,
                            draft_id,
                            relative_db_path,
                            utc_now(),
                        ),
                    )
                    row = self._connection.execute(
                        "SELECT * FROM world_creation_intents WHERE request_id = ?",
                        (request_id,),
                    ).fetchone()
                elif row["world_id"] != world_id:
                    raise ValueError(
                        f"creation request already belongs to world: {request_id}"
                    )
            except BaseException:
                self._connection.rollback()
                raise
            else:
                self._connection.commit()
        return self._row_to_creation_intent(row)

    def pending_creation_intents(self) -> list[dict[str, Any]]:
        """List creation intents that still need catalog recovery."""

        with self._lock:
            rows = self._connection.execute(
                """SELECT * FROM world_creation_intents
                WHERE status = 'pending' ORDER BY created_at, request_id"""
            ).fetchall()
        return [self._row_to_creation_intent(row) for row in rows]

    def creation_intent_for_request(self, request_id: str) -> dict[str, Any] | None:
        """Load one pending creation intent for same-request recovery."""

        with self._lock:
            row = self._connection.execute(
                """SELECT * FROM world_creation_intents
                WHERE request_id = ? AND status = 'pending'""",
                (request_id,),
            ).fetchone()
        return self._row_to_creation_intent(row) if row is not None else None

    def discard_creation_intent(self, request_id: str) -> None:
        """Remove an intent whose database was never committed."""

        with self._lock:
            self._connection.execute(
                """DELETE FROM world_creation_intents
                WHERE request_id = ? AND status = 'pending'""",
                (request_id,),
            )

    def complete_world(
        self,
        *,
        draft_id: str | None,
        world_id: str,
        relative_db_path: str,
        summary: dict[str, Any],
        request_id: str,
    ) -> None:
        """Make one fully created world discoverable and record request idempotency."""

        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                entry = self._connection.execute(
                    "SELECT relative_db_path FROM world_entries WHERE world_id = ?",
                    (world_id,),
                ).fetchone()
                if entry is None:
                    self._connection.execute(
                        "INSERT INTO world_entries VALUES (?, ?, ?, ?)",
                        (world_id, relative_db_path, _dump(summary), utc_now()),
                    )
                elif entry["relative_db_path"] != relative_db_path:
                    raise ValueError(f"world path changed: {world_id}")
                else:
                    self._connection.execute(
                        "UPDATE world_entries SET summary = ? WHERE world_id = ?",
                        (_dump(summary), world_id),
                    )
                request = self._connection.execute(
                    "SELECT world_id FROM catalog_idempotency WHERE request_id = ?",
                    (request_id,),
                ).fetchone()
                if request is None:
                    self._connection.execute(
                        "INSERT INTO catalog_idempotency VALUES (?, ?)",
                        (request_id, world_id),
                    )
                elif request["world_id"] != world_id:
                    raise ValueError(
                        f"catalog request already belongs to world: {request_id}"
                    )
                if draft_id is not None:
                    updated = self._connection.execute(
                        """UPDATE world_drafts SET status = 'confirmed'
                        WHERE id = ? AND status IN ('draft', 'confirmed')""",
                        (draft_id,),
                    )
                    if updated.rowcount != 1:
                        raise WorldNotFoundError(
                            f"world draft is not confirmable: {draft_id}"
                        )
                self._connection.execute(
                    """UPDATE world_creation_intents
                    SET status = 'completed', completed_at = ?
                    WHERE request_id = ? AND world_id = ?""",
                    (utc_now(), request_id, world_id),
                )
            except BaseException:
                self._connection.rollback()
                raise
            else:
                self._connection.commit()

    def world_id_for_request(self, request_id: str) -> str | None:
        """Resolve catalog-scoped creation idempotency."""

        with self._lock:
            row = self._connection.execute(
                "SELECT world_id FROM catalog_idempotency WHERE request_id = ?",
                (request_id,),
            ).fetchone()
        return str(row["world_id"]) if row is not None else None

    def relative_db_path(self, world_id: str) -> str:
        """Return the registered relative database path for one world."""

        with self._lock:
            row = self._connection.execute(
                "SELECT relative_db_path FROM world_entries WHERE world_id = ?",
                (world_id,),
            ).fetchone()
        if row is None:
            raise WorldNotFoundError(f"world not found: {world_id}")
        return str(row["relative_db_path"])

    def list_summaries(self) -> list[dict[str, Any]]:
        """List cached desktop summaries without opening world databases."""

        with self._lock:
            rows = self._connection.execute(
                "SELECT summary FROM world_entries ORDER BY created_at, world_id"
            ).fetchall()
        return [_load(row["summary"], {}) for row in rows]

    def update_summary(self, world_id: str, summary: dict[str, Any]) -> None:
        """Synchronize the catalog projection after a committed world mutation."""

        with self._lock:
            updated = self._connection.execute(
                "UPDATE world_entries SET summary = ? WHERE world_id = ?",
                (_dump(summary), world_id),
            )
        if updated.rowcount != 1:
            raise WorldNotFoundError(f"world not found: {world_id}")

    @staticmethod
    def _row_to_creation_intent(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "request_id": row["request_id"],
            "world_id": row["world_id"],
            "draft_id": row["draft_id"],
            "relative_db_path": row["relative_db_path"],
            "status": row["status"],
            "created_at": row["created_at"],
            "completed_at": row["completed_at"],
        }

    @staticmethod
    def _draft_payload(draft: WorldDraft) -> dict[str, Any]:
        return {
            "template": draft.template.to_dict(),
            "role_snapshots": [item.to_dict() for item in draft.role_snapshots],
            "residents": [item.to_dict() for item in draft.residents],
            "initial_time": draft.initial_time,
            "creation_metadata": draft.creation_metadata,
        }

    @staticmethod
    def _row_to_draft(row: sqlite3.Row) -> WorldDraft:
        payload = _load(row["payload"], {})
        return WorldDraft(
            id=row["id"],
            owner_id=row["owner_id"],
            template=WorldTemplate(**payload["template"]),
            role_snapshots=tuple(
                RoleTemplateSnapshot(**item) for item in payload["role_snapshots"]
            ),
            residents=tuple(NativeResident(**item) for item in payload["residents"]),
            initial_time=payload["initial_time"],
            creation_metadata=dict(payload.get("creation_metadata", {})),
            status=row["status"],
            created_at=row["created_at"],
        )
