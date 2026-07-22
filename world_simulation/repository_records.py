"""Low-level record encoding and prefix-copy transactions for world storage."""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from world_simulation.dependencies import DependencySet
from world_simulation.errors import StaleWorldRevisionError, WorldNotFoundError
from world_simulation.runs import WorldRun
from world_simulation.timeline import TimelineEvent, WorldStateProjection
from world_simulation.world import WorldInstance, utc_now


def _dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _load(value: str | None, default: Any) -> Any:
    return json.loads(value) if value else default


class RepositoryRecords:
    """Implementation details shared by the public SQLite repository facade."""

    def copy_world_prefix(
        self,
        *,
        source_world_id: str,
        through_event: TimelineEvent,
        target: WorldInstance,
        projection: WorldStateProjection,
        request_id: str,
        result: dict[str, Any],
    ) -> dict[str, Any]:
        """Create an independent world from a committed timeline prefix."""

        with self.transaction() as connection:
            existing = self._idempotency_in(connection, request_id)
            if existing is not None:
                return existing
            source = connection.execute(
                "SELECT * FROM worlds WHERE id = ?", (source_world_id,)
            ).fetchone()
            if source is None:
                raise WorldNotFoundError(f"world not found: {source_world_id}")
            connection.execute(
                "INSERT INTO worlds VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    target.id,
                    target.owner_id,
                    _dump(target.template_snapshot),
                    target.current_time,
                    target.revision,
                    target.active_oc_id,
                    target.parent_world_id,
                    target.fork_event_id,
                    target.random_state,
                    target.created_at,
                ),
            )
            for table in ("role_snapshots", "residents"):
                connection.execute(
                    f"INSERT INTO {table} SELECT id, ?, payload FROM {table} WHERE world_id = ?",
                    (target.id, source_world_id),
                )
            connection.execute(
                """INSERT INTO player_ocs
                SELECT id, ?, payload, joined_at FROM player_ocs
                WHERE world_id = ? AND joined_at <= ?""",
                (target.id, source_world_id, through_event.effective_at),
            )
            rows = connection.execute(
                """SELECT * FROM timeline_events WHERE world_id = ? AND sequence <= ?
                ORDER BY sequence""",
                (source_world_id, through_event.sequence),
            ).fetchall()
            for row in rows:
                event = self._row_to_event(row)
                copied = TimelineEvent(
                    **{
                        **event.to_dict(),
                        "world_id": target.id,
                        "dependencies": event.dependencies,
                    }
                )
                self._insert_event(connection, copied)
            self._upsert_projection(connection, projection)
            self._save_idempotency(connection, request_id, target.id, result)
            self._insert_outbox(
                connection,
                event_id=f"outbox:world-copied:{target.id}",
                world_id=target.id,
                event_type="WorldCopied",
                payload=result,
            )
            return result

    def _assert_revision(
        self, connection: sqlite3.Connection, world_id: str, expected: int
    ) -> None:
        row = connection.execute(
            "SELECT revision FROM worlds WHERE id = ?", (world_id,)
        ).fetchone()
        if row is None:
            raise WorldNotFoundError(f"world not found: {world_id}")
        actual = int(row["revision"])
        if actual != expected:
            raise StaleWorldRevisionError(
                f"stale world revision: expected {expected}, actual {actual}"
            )

    def _insert_event(
        self, connection: sqlite3.Connection, event: TimelineEvent
    ) -> None:
        connection.execute(
            "INSERT INTO timeline_events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                event.id,
                event.world_id,
                event.event_type,
                event.effective_at,
                event.sequence,
                event.recorded_at,
                _dump(event.to_dict()),
                _dump(event.dependencies.to_dict()),
                event.request_id,
                event.committed_revision,
                int(event.is_backfill),
            ),
        )

    def _upsert_projection(
        self, connection: sqlite3.Connection, projection: WorldStateProjection
    ) -> None:
        connection.execute(
            """INSERT INTO projections VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(world_id) DO UPDATE SET revision = excluded.revision,
            state = excluded.state, cognition = excluded.cognition,
            invalid_after = excluded.invalid_after""",
            (
                projection.world_id,
                projection.revision,
                _dump(projection.state),
                _dump(projection.cognition),
                projection.invalid_after,
            ),
        )
        connection.execute(
            """INSERT INTO projection_history VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(world_id, revision) DO UPDATE SET
            state = excluded.state, cognition = excluded.cognition,
            invalid_after = excluded.invalid_after""",
            (
                projection.world_id,
                projection.revision,
                _dump(projection.state),
                _dump(projection.cognition),
                projection.invalid_after,
            ),
        )

    def _insert_outbox(
        self,
        connection: sqlite3.Connection,
        *,
        event_id: str,
        world_id: str,
        event_type: str,
        payload: dict[str, Any],
    ) -> None:
        connection.execute(
            "INSERT INTO outbox(event_id, world_id, event_type, payload, created_at) VALUES (?, ?, ?, ?, ?)",
            (event_id, world_id, event_type, _dump(payload), utc_now()),
        )

    def _save_idempotency(
        self,
        connection: sqlite3.Connection,
        request_id: str,
        world_id: str,
        result: dict[str, Any],
    ) -> None:
        connection.execute(
            "INSERT INTO idempotency_results VALUES (?, ?, ?, ?)",
            (request_id, world_id, _dump(result), utc_now()),
        )

    @staticmethod
    def _idempotency_in(
        connection: sqlite3.Connection, request_id: str
    ) -> dict[str, Any] | None:
        row = connection.execute(
            "SELECT result FROM idempotency_results WHERE request_id = ?", (request_id,)
        ).fetchone()
        return _load(row["result"], {}) if row else None

    def _save_run_in(self, connection: sqlite3.Connection, run: WorldRun) -> None:
        connection.execute(
            """INSERT INTO world_runs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET status = excluded.status,
            last_committed_revision = excluded.last_committed_revision,
            error = excluded.error, updated_at = excluded.updated_at""",
            (
                run.id,
                run.request_id,
                run.world_id,
                run.kind,
                run.status,
                run.starting_revision,
                run.last_committed_revision,
                run.random_seed,
                _dump(run.error) if run.error else None,
                run.created_at,
                run.updated_at,
            ),
        )

    @staticmethod
    def _row_to_world(row: sqlite3.Row) -> WorldInstance:
        return WorldInstance(
            id=row["id"],
            owner_id=row["owner_id"],
            template_snapshot=_load(row["template_snapshot"], {}),
            current_time=row["current_time"],
            revision=int(row["revision"]),
            active_oc_id=row["active_oc_id"],
            parent_world_id=row["parent_world_id"],
            fork_event_id=row["fork_event_id"],
            random_state=row["random_state"],
            created_at=row["created_at"],
        )

    @staticmethod
    def _row_to_event(row: sqlite3.Row) -> TimelineEvent:
        payload = _load(row["payload"], {})
        payload["participants"] = tuple(payload.get("participants", ()))
        payload["cause_event_ids"] = tuple(payload.get("cause_event_ids", ()))
        payload["dependencies"] = DependencySet.from_dict(
            _load(row["dependencies"], {})
        )
        return TimelineEvent(**payload)

    @staticmethod
    def _row_to_run(row: sqlite3.Row) -> WorldRun:
        return WorldRun(
            id=row["id"],
            request_id=row["request_id"],
            world_id=row["world_id"],
            kind=row["kind"],
            starting_revision=int(row["starting_revision"]),
            random_seed=row["random_seed"],
            status=row["status"],
            last_committed_revision=row["last_committed_revision"],
            error=_load(row["error"], None),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
