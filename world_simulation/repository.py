"""Transactional SQLite persistence for the persistent world bounded context."""

from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Sequence

from world_simulation._schema import SCHEMA
from world_simulation.actors import AutonomyPolicy, PlayerOC
from world_simulation.errors import WorldNotFoundError
from world_simulation.repository_records import RepositoryRecords, _dump, _load
from world_simulation.runs import WorldRun
from world_simulation.scenes import DecisionBarrier, SceneThread
from world_simulation.timeline import TimelineEvent, WorldStateProjection
from world_simulation.world import (
    NativeResident,
    RoleTemplateSnapshot,
    WorldDraft,
    WorldInstance,
    WorldTemplate,
)


class WorldRepository(RepositoryRecords):
    """Own all durable world facts, projections, runs, idempotency, and outbox state."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(
            str(self.db_path), check_same_thread=False, isolation_level=None
        )
        self._connection.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        with self._lock:
            self._connection.executescript(SCHEMA)

    def close(self) -> None:
        """Close the underlying SQLite connection."""

        with self._lock:
            self._connection.close()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """Serialize one immediate SQLite transaction and roll it back on failure."""

        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                yield self._connection
            except BaseException:
                self._connection.rollback()
                raise
            else:
                self._connection.commit()

    def save_draft(self, draft: WorldDraft) -> None:
        """Persist a reviewable creation draft without creating world facts."""

        payload = {
            "template": draft.template.to_dict(),
            "role_snapshots": [item.to_dict() for item in draft.role_snapshots],
            "residents": [item.to_dict() for item in draft.residents],
            "initial_time": draft.initial_time,
            "creation_metadata": draft.creation_metadata,
        }
        with self.transaction() as connection:
            connection.execute(
                "INSERT INTO world_drafts VALUES (?, ?, ?, ?, ?)",
                (draft.id, draft.owner_id, _dump(payload), draft.status, draft.created_at),
            )

    def get_draft(self, draft_id: str) -> WorldDraft | None:
        """Load a creation draft by id."""

        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM world_drafts WHERE id = ?", (draft_id,)
            ).fetchone()
        if row is None:
            return None
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

    def replace_draft(self, draft: WorldDraft) -> None:
        """Persist player-approved draft edits before the world is confirmed."""

        payload = {
            "template": draft.template.to_dict(),
            "role_snapshots": [item.to_dict() for item in draft.role_snapshots],
            "residents": [item.to_dict() for item in draft.residents],
            "initial_time": draft.initial_time,
            "creation_metadata": draft.creation_metadata,
        }
        with self.transaction() as connection:
            updated = connection.execute(
                """UPDATE world_drafts SET payload = ?
                WHERE id = ? AND status = 'draft'""",
                (_dump(payload), draft.id),
            )
            if updated.rowcount != 1:
                raise WorldNotFoundError(f"world draft is not editable: {draft.id}")

    def create_world_from_draft(
        self,
        draft: WorldDraft,
        world: WorldInstance,
        initial_event: TimelineEvent,
        projection: WorldStateProjection,
        *,
        request_id: str,
        result: dict[str, Any],
        initial_oc: PlayerOC | None = None,
    ) -> None:
        """Atomically confirm a draft into a complete initial world."""

        with self.transaction() as connection:
            existing = self._idempotency_in(connection, request_id)
            if existing is not None:
                return
            connection.execute(
                """INSERT INTO worlds
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    world.id,
                    world.owner_id,
                    _dump(world.template_snapshot),
                    world.current_time,
                    world.revision,
                    world.active_oc_id,
                    world.parent_world_id,
                    world.fork_event_id,
                    world.random_state,
                    world.created_at,
                ),
            )
            connection.executemany(
                "INSERT INTO role_snapshots VALUES (?, ?, ?)",
                [(item.id, world.id, _dump(item.to_dict())) for item in draft.role_snapshots],
            )
            connection.executemany(
                "INSERT INTO residents VALUES (?, ?, ?)",
                [(item.id, world.id, _dump(item.to_dict())) for item in draft.residents],
            )
            if initial_oc is not None:
                connection.execute(
                    "INSERT INTO player_ocs VALUES (?, ?, ?, ?)",
                    (
                        initial_oc.id,
                        world.id,
                        _dump(initial_oc.to_dict()),
                        world.current_time,
                    ),
                )
            self._insert_event(connection, initial_event)
            self._upsert_projection(connection, projection)
            connection.execute(
                "UPDATE world_drafts SET status = 'confirmed' WHERE id = ?",
                (draft.id,),
            )
            self._insert_outbox(
                connection,
                event_id=f"outbox:{initial_event.id}",
                world_id=world.id,
                event_type="SceneBeatCommitted",
                payload={"event": initial_event.to_dict(), "world_revision": world.revision},
            )
            self._save_idempotency(connection, request_id, world.id, result)

    def get_world(self, world_id: str) -> WorldInstance | None:
        """Load one current world instance."""

        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM worlds WHERE id = ?", (world_id,)
            ).fetchone()
        return self._row_to_world(row) if row is not None else None

    def list_worlds(self) -> list[WorldInstance]:
        """Return worlds in creation order without exposing repository internals."""

        with self._lock:
            rows = self._connection.execute(
                "SELECT * FROM worlds ORDER BY created_at, id"
            ).fetchall()
        return [self._row_to_world(row) for row in rows]

    def list_residents(self, world_id: str) -> list[NativeResident]:
        """Return immutable native residents owned by one world."""

        with self._lock:
            rows = self._connection.execute(
                "SELECT payload FROM residents WHERE world_id = ? ORDER BY id",
                (world_id,),
            ).fetchall()
        return [NativeResident(**_load(row["payload"], {})) for row in rows]

    def require_world(self, world_id: str) -> WorldInstance:
        """Load a world or fail with a stable domain error."""

        world = self.get_world(world_id)
        if world is None:
            raise WorldNotFoundError(f"world not found: {world_id}")
        return world

    def update_active_oc(
        self, world_id: str, oc_id: str, expected_revision: int
    ) -> WorldInstance:
        """Switch control without advancing world time or revision."""

        with self.transaction() as connection:
            self._assert_revision(connection, world_id, expected_revision)
            exists = connection.execute(
                "SELECT 1 FROM player_ocs WHERE world_id = ? AND id = ?",
                (world_id, oc_id),
            ).fetchone()
            if exists is None:
                raise WorldNotFoundError(f"player OC not found: {oc_id}")
            connection.execute(
                "UPDATE worlds SET active_oc_id = ? WHERE id = ?", (oc_id, world_id)
            )
        return self.require_world(world_id)

    def add_oc(
        self,
        world_id: str,
        oc: PlayerOC,
        joined_at: str,
        *,
        expected_revision: int,
        request_id: str,
        event: TimelineEvent,
        projection: WorldStateProjection,
        result: dict[str, Any],
    ) -> dict[str, Any]:
        """Atomically add an OC, its timeline fact, projection, and outbox entry."""

        with self.transaction() as connection:
            existing = self._idempotency_in(connection, request_id)
            if existing is not None:
                return existing
            self._assert_revision(connection, world_id, expected_revision)
            connection.execute(
                "INSERT INTO player_ocs VALUES (?, ?, ?, ?)",
                (oc.id, world_id, _dump(oc.to_dict()), joined_at),
            )
            connection.execute(
                """UPDATE worlds SET revision = ?, active_oc_id = COALESCE(active_oc_id, ?)
                WHERE id = ?""",
                (event.committed_revision, oc.id, world_id),
            )
            self._insert_event(connection, event)
            self._upsert_projection(connection, projection)
            self._insert_outbox(
                connection,
                event_id=f"outbox:{event.id}",
                world_id=world_id,
                event_type="SceneBeatCommitted",
                payload={"event": event.to_dict(), "world_revision": event.committed_revision},
            )
            self._save_idempotency(connection, request_id, world_id, result)
            return result

    def list_ocs(self, world_id: str) -> list[PlayerOC]:
        """List all player identities in one world."""

        with self._lock:
            rows = self._connection.execute(
                "SELECT payload FROM player_ocs WHERE world_id = ? ORDER BY id", (world_id,)
            ).fetchall()
        values = []
        for row in rows:
            payload = _load(row["payload"], {})
            payload["autonomy"] = AutonomyPolicy(**payload.get("autonomy", {}))
            values.append(PlayerOC(**payload))
        return values

    def get_projection(self, world_id: str) -> WorldStateProjection:
        """Load the rebuildable current projection."""

        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM projections WHERE world_id = ?", (world_id,)
            ).fetchone()
        if row is None:
            raise WorldNotFoundError(f"world projection not found: {world_id}")
        return WorldStateProjection(
            world_id=world_id,
            revision=int(row["revision"]),
            state=_load(row["state"], {}),
            cognition=_load(row["cognition"], {}),
            invalid_after=row["invalid_after"],
        )

    def get_projection_at_revision(
        self, world_id: str, revision: int
    ) -> WorldStateProjection | None:
        """Load the cached projection associated with a committed revision."""

        with self._lock:
            row = self._connection.execute(
                """SELECT * FROM projection_history
                WHERE world_id = ? AND revision = ?""",
                (world_id, revision),
            ).fetchone()
        if row is None:
            return None
        return WorldStateProjection(
            world_id=world_id,
            revision=int(row["revision"]),
            state=_load(row["state"], {}),
            cognition=_load(row["cognition"], {}),
            invalid_after=row["invalid_after"],
        )

    def list_events(
        self, world_id: str, *, through_sequence: int | None = None
    ) -> list[TimelineEvent]:
        """List events in immutable write order."""

        query = "SELECT * FROM timeline_events WHERE world_id = ?"
        params: list[Any] = [world_id]
        if through_sequence is not None:
            query += " AND sequence <= ?"
            params.append(through_sequence)
        query += " ORDER BY sequence"
        with self._lock:
            rows = self._connection.execute(query, params).fetchall()
        return [self._row_to_event(row) for row in rows]

    def get_event(self, world_id: str, event_id: str) -> TimelineEvent | None:
        """Load one committed event."""

        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM timeline_events WHERE world_id = ? AND id = ?",
                (world_id, event_id),
            ).fetchone()
        return self._row_to_event(row) if row is not None else None

    def list_events_after_effective_at(
        self, world_id: str, effective_at: str
    ) -> list[TimelineEvent]:
        """List settled events whose causal basis may be affected by a backfill."""

        with self._lock:
            rows = self._connection.execute(
                """SELECT * FROM timeline_events
                WHERE world_id = ? AND effective_at >= ? ORDER BY sequence""",
                (world_id, effective_at),
            ).fetchall()
        return [self._row_to_event(row) for row in rows]

    def next_event_sequence(self, world_id: str) -> int:
        """Return the next immutable write sequence for a world."""

        with self._lock:
            row = self._connection.execute(
                "SELECT COALESCE(MAX(sequence), 0) + 1 AS value FROM timeline_events WHERE world_id = ?",
                (world_id,),
            ).fetchone()
        return int(row["value"])

    def list_pending_barriers(self, world_id: str) -> list[DecisionBarrier]:
        """List unresolved barriers in deterministic world-time order."""

        with self._lock:
            rows = self._connection.execute(
                """SELECT payload FROM barriers WHERE world_id = ? AND status = 'pending'
                ORDER BY effective_at, id""",
                (world_id,),
            ).fetchall()
        return [DecisionBarrier(**_load(row["payload"], {})) for row in rows]

    def get_barrier(self, world_id: str, barrier_id: str) -> DecisionBarrier | None:
        """Load one decision barrier."""

        with self._lock:
            row = self._connection.execute(
                "SELECT payload FROM barriers WHERE world_id = ? AND id = ?",
                (world_id, barrier_id),
            ).fetchone()
        return DecisionBarrier(**_load(row["payload"], {})) if row else None

    def save_run(self, run: WorldRun) -> None:
        """Persist or update a recoverable run state."""

        with self.transaction() as connection:
            self._save_run_in(connection, run)

    def get_run(self, run_id: str) -> WorldRun | None:
        """Load one world run."""

        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM world_runs WHERE id = ?", (run_id,)
            ).fetchone()
        return self._row_to_run(row) if row is not None else None

    def get_run_by_request(self, request_id: str) -> WorldRun | None:
        """Load the stable run previously created for an idempotent request."""

        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM world_runs WHERE request_id = ?", (request_id,)
            ).fetchone()
        return self._row_to_run(row) if row is not None else None

    def list_runs(self, world_id: str) -> list[WorldRun]:
        """Return a world's recoverable runs from newest to oldest."""

        with self._lock:
            rows = self._connection.execute(
                "SELECT * FROM world_runs WHERE world_id = ? ORDER BY updated_at DESC, id DESC",
                (world_id,),
            ).fetchall()
        return [self._row_to_run(row) for row in rows]

    def get_idempotency_result(self, request_id: str) -> dict[str, Any] | None:
        """Return the exact result previously committed for a request."""

        with self._lock:
            return self._idempotency_in(self._connection, request_id)

    def commit_beat(
        self,
        *,
        world_id: str,
        expected_revision: int,
        request_id: str,
        events: Sequence[TimelineEvent],
        projection: WorldStateProjection,
        current_time: str,
        result: dict[str, Any],
        run: WorldRun | None = None,
        barrier: DecisionBarrier | None = None,
        resolved_barrier: DecisionBarrier | None = None,
        scene_thread: SceneThread | None = None,
    ) -> dict[str, Any]:
        """Atomically commit facts, projection, idempotency, outbox, and run state."""

        with self.transaction() as connection:
            existing = self._idempotency_in(connection, request_id)
            if existing is not None:
                return existing
            self._assert_revision(connection, world_id, expected_revision)
            connection.execute(
                "UPDATE worlds SET revision = ?, current_time = ? WHERE id = ?",
                (projection.revision, current_time, world_id),
            )
            for event in events:
                self._insert_event(connection, event)
            self._upsert_projection(connection, projection)
            if barrier is not None:
                connection.execute(
                    "INSERT INTO barriers VALUES (?, ?, ?, ?, ?)",
                    (
                        barrier.id,
                        world_id,
                        barrier.effective_at,
                        barrier.status,
                        _dump(barrier.to_dict()),
                    ),
                )
            if resolved_barrier is not None:
                connection.execute(
                    """UPDATE barriers SET status = ?, payload = ?
                    WHERE world_id = ? AND id = ?""",
                    (
                        resolved_barrier.status,
                        _dump(resolved_barrier.to_dict()),
                        world_id,
                        resolved_barrier.id,
                    ),
                )
            if scene_thread is not None:
                connection.execute(
                    """INSERT INTO scene_threads VALUES (?, ?, ?)
                    ON CONFLICT(world_id, id) DO UPDATE SET payload = excluded.payload""",
                    (scene_thread.id, world_id, _dump(scene_thread.to_dict())),
                )
            if run is not None:
                self._save_run_in(connection, run)
            for event in events:
                self._insert_outbox(
                    connection,
                    event_id=f"outbox:{event.id}",
                    world_id=world_id,
                    event_type="SceneBeatCommitted",
                    payload={"event": event.to_dict(), "world_revision": projection.revision},
                )
            self._save_idempotency(connection, request_id, world_id, result)
            return result

    def list_outbox(
        self, world_id: str, *, after_sequence: int = 0, limit: int = 100
    ) -> list[dict[str, Any]]:
        """Replay durable world notifications after a consumer cursor."""

        with self._lock:
            rows = self._connection.execute(
                """SELECT * FROM outbox WHERE world_id = ? AND sequence > ?
                ORDER BY sequence LIMIT ?""",
                (world_id, after_sequence, limit),
            ).fetchall()
        return [
            {
                "sequence": int(row["sequence"]),
                "event_id": row["event_id"],
                "world_id": row["world_id"],
                "event_type": row["event_type"],
                "payload": _load(row["payload"], {}),
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def acknowledge_outbox(
        self, consumer_id: str, world_id: str, sequence: int
    ) -> None:
        """Advance a durable consumer cursor monotonically."""

        with self.transaction() as connection:
            connection.execute(
                """INSERT INTO outbox_consumers VALUES (?, ?, ?)
                ON CONFLICT(consumer_id, world_id) DO UPDATE SET
                acknowledged_sequence = MAX(acknowledged_sequence, excluded.acknowledged_sequence)""",
                (consumer_id, world_id, sequence),
            )

    def consumer_cursor(self, consumer_id: str, world_id: str) -> int:
        """Return the last durable outbox acknowledgement for a consumer."""

        with self._lock:
            row = self._connection.execute(
                """SELECT acknowledged_sequence FROM outbox_consumers
                WHERE consumer_id = ? AND world_id = ?""",
                (consumer_id, world_id),
            ).fetchone()
        return int(row["acknowledged_sequence"]) if row else 0
