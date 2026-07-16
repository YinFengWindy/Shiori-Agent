"""Immutable plan snapshot persistence for CodingAgentStore."""

from __future__ import annotations

import sqlite3
import threading
from collections.abc import Mapping
from contextlib import AbstractContextManager
from typing import Any

from .models import PlanSnapshot, utc_now
from .store_rows import dump_json, row_to_plan_snapshot


class StorePlansMixin:
    """Persist confirmed plan versions and their audit events."""

    _connection: sqlite3.Connection
    _lock: threading.RLock

    def _transaction(self) -> AbstractContextManager[None]:
        raise NotImplementedError

    def _append_event_locked(
        self,
        *,
        task_id: str,
        run_id: str | None,
        event_type: str,
        request_id: str,
        previous_status: str | None,
        next_status: str | None,
        payload: Mapping[str, Any] | None,
    ):
        raise NotImplementedError

    def create_plan_snapshot(
        self, snapshot: PlanSnapshot, *, request_id: str
    ) -> PlanSnapshot:
        """Persist an immutable plan version and append its confirmation event."""

        with self._transaction():
            self._connection.execute(
                """INSERT INTO coding_plan_snapshots
                   (id, task_id, version, content, source_run_ids_json,
                    confirmed_by, confirmed_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    snapshot.id,
                    snapshot.task_id,
                    snapshot.version,
                    snapshot.content,
                    dump_json(snapshot.source_run_ids),
                    snapshot.confirmed_by,
                    snapshot.confirmed_at,
                ),
            )
            self._connection.execute(
                "UPDATE coding_tasks SET plan_snapshot_id = ?, updated_at = ? WHERE id = ?",
                (snapshot.id, utc_now(), snapshot.task_id),
            )
            self._append_event_locked(
                task_id=snapshot.task_id,
                run_id=None,
                event_type="plan_confirmed",
                request_id=request_id,
                previous_status=None,
                next_status=None,
                payload={"plan_snapshot_id": snapshot.id, "version": snapshot.version},
            )
            return snapshot

    def get_plan_snapshot(self, snapshot_id: str) -> PlanSnapshot | None:
        """Return an immutable plan snapshot by ID."""

        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM coding_plan_snapshots WHERE id = ?", (snapshot_id,)
            ).fetchone()
            return row_to_plan_snapshot(row) if row else None

    def list_plan_snapshots(self, task_id: str) -> list[PlanSnapshot]:
        """List immutable plan versions for one task in ascending order."""

        with self._lock:
            rows = self._connection.execute(
                "SELECT * FROM coding_plan_snapshots WHERE task_id = ? ORDER BY version",
                (task_id,),
            ).fetchall()
            return [row_to_plan_snapshot(row) for row in rows]

    create_coding_plan_snapshot = create_plan_snapshot
    get_coding_plan_snapshot = get_plan_snapshot
