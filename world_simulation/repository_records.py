"""Low-level record encoding and prefix-copy transactions for world storage."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import replace
from typing import TYPE_CHECKING, Any, Sequence

from world_simulation.dependencies import DependencySet
from world_simulation.errors import StaleWorldRevisionError, WorldNotFoundError
from world_simulation.performance import compile_performance_plan, presentation_mode_for_event
from world_simulation.presentation_session import WorldPresentationSession
from world_simulation.runs import WorldRun
from world_simulation.scenes import DecisionBarrier, SceneThread
from world_simulation.timeline import TimelineEvent, WorldStateProjection
from world_simulation.world import (
    NativeResident,
    RoleTemplateSnapshot,
    WorldInstance,
    utc_now,
)

if TYPE_CHECKING:
    from world_simulation.repository import WorldRepository


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
            snapshots = [
                RoleTemplateSnapshot(**_load(row["payload"], {}))
                for row in connection.execute(
                    "SELECT payload FROM role_snapshots WHERE world_id = ? ORDER BY id",
                    (source_world_id,),
                ).fetchall()
            ]
            residents = [
                NativeResident(**_load(row["payload"], {}))
                for row in connection.execute(
                    "SELECT payload FROM residents WHERE world_id = ? ORDER BY id",
                    (source_world_id,),
                ).fetchall()
            ]
            memberships = [
                (
                    self._row_to_oc(row),
                    row["joined_at"],
                )
                for row in connection.execute(
                    """SELECT payload, joined_at FROM player_ocs
                    WHERE world_id = ? AND joined_at <= ? ORDER BY id""",
                    (source_world_id, through_event.effective_at),
                ).fetchall()
            ]
            events = connection.execute(
                """SELECT * FROM timeline_events WHERE world_id = ? AND sequence <= ?
                ORDER BY sequence""",
                (source_world_id, through_event.sequence),
            ).fetchall()
            barriers = [
                DecisionBarrier(**_load(row["payload"], {}))
                for row in connection.execute(
                    """SELECT payload FROM barriers
                    WHERE world_id = ? AND effective_at <= ?
                    ORDER BY effective_at, id""",
                    (source_world_id, through_event.effective_at),
                ).fetchall()
            ]
            scene_threads = [
                thread
                for thread in (
                    SceneThread(**_load(row["payload"], {}))
                    for row in connection.execute(
                        "SELECT payload FROM scene_threads WHERE world_id = ?",
                        (source_world_id,),
                    ).fetchall()
                )
                if (
                    thread.world_time <= through_event.effective_at
                    and thread.beat_sequence <= through_event.sequence
                )
            ]
            presentation_session = self.get_presentation_session(source_world_id)
            return self._copy_world_prefix_in(
                connection,
                source_world_id=source_world_id,
                through_event=through_event,
                target=target,
                projection=projection,
                request_id=request_id,
                result=result,
                snapshots=snapshots,
                residents=residents,
                memberships=memberships,
                events=[self._row_to_event(row) for row in events],
                barriers=barriers,
                scene_threads=scene_threads,
                presentation_session=presentation_session,
            )

    def copy_world_prefix_from(
        self,
        source_repository: WorldRepository,
        *,
        source_world_id: str,
        through_event: TimelineEvent,
        target: WorldInstance,
        projection: WorldStateProjection,
        request_id: str,
        result: dict[str, Any],
    ) -> dict[str, Any]:
        """Copy a stable source prefix into this repository's target database."""

        if source_repository is self:
            return self.copy_world_prefix(
                source_world_id=source_world_id,
                through_event=through_event,
                target=target,
                projection=projection,
                request_id=request_id,
                result=result,
            )
        source_repository.require_world(source_world_id)
        snapshots = source_repository.list_role_snapshots(source_world_id)
        residents = source_repository.list_residents(source_world_id)
        memberships = source_repository.list_oc_memberships(
            source_world_id, through_time=through_event.effective_at
        )
        events = source_repository.list_events(
            source_world_id, through_sequence=through_event.sequence
        )
        barriers = source_repository.list_barriers(
            source_world_id, through_time=through_event.effective_at
        )
        scene_threads = source_repository.list_scene_threads(
            source_world_id,
            through_time=through_event.effective_at,
            through_sequence=through_event.sequence,
        )
        presentation_session = source_repository.get_presentation_session(
            source_world_id
        )

        with self.transaction() as connection:
            existing = self._idempotency_in(connection, request_id)
            if existing is not None:
                return existing
            return self._copy_world_prefix_in(
                connection,
                source_world_id=source_world_id,
                through_event=through_event,
                target=target,
                projection=projection,
                request_id=request_id,
                result=result,
                snapshots=snapshots,
                residents=residents,
                memberships=memberships,
                events=events,
                barriers=barriers,
                scene_threads=scene_threads,
                presentation_session=presentation_session,
            )

    def _copy_world_prefix_in(
        self,
        connection: sqlite3.Connection,
        *,
        source_world_id: str,
        through_event: TimelineEvent,
        target: WorldInstance,
        projection: WorldStateProjection,
        request_id: str,
        result: dict[str, Any],
        snapshots: Sequence[RoleTemplateSnapshot],
        residents: Sequence[NativeResident],
        memberships: Sequence[tuple[Any, str]],
        events: Sequence[TimelineEvent],
        barriers: Sequence[DecisionBarrier],
        scene_threads: Sequence[SceneThread],
        presentation_session: WorldPresentationSession | None,
    ) -> dict[str, Any]:
        """Write one copied prefix while the caller owns the target transaction."""

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
        connection.executemany(
            "INSERT INTO role_snapshots VALUES (?, ?, ?)",
            [(item.id, target.id, _dump(item.to_dict())) for item in snapshots],
        )
        connection.executemany(
            "INSERT INTO residents VALUES (?, ?, ?)",
            [(item.id, target.id, _dump(item.to_dict())) for item in residents],
        )
        connection.executemany(
            "INSERT INTO player_ocs VALUES (?, ?, ?, ?)",
            [
                (oc.id, target.id, _dump(oc.to_dict()), joined_at)
                for oc, joined_at in memberships
            ],
        )
        copied_events = [
            TimelineEvent(
                **{
                    **event.to_dict(),
                    "world_id": target.id,
                    "dependencies": event.dependencies,
                }
            )
            for event in events
        ]
        for event in copied_events:
            self._insert_event(connection, event)
        for barrier in barriers:
            copied = replace(barrier, world_id=target.id)
            connection.execute(
                "INSERT INTO barriers VALUES (?, ?, ?, ?, ?)",
                (
                    copied.id,
                    target.id,
                    copied.effective_at,
                    copied.status,
                    _dump(copied.to_dict()),
                ),
            )
        for thread in scene_threads:
            copied = replace(thread, world_id=target.id)
            connection.execute(
                "INSERT INTO scene_threads VALUES (?, ?, ?)",
                (copied.id, target.id, _dump(copied.to_dict())),
            )
        self._upsert_projection(connection, projection)
        copied_session = self._copy_presentation_session(
            presentation_session,
            target.id,
            through_event.sequence,
            events,
            copied_events,
            barriers,
        )
        connection.execute(
            """INSERT INTO world_presentation_sessions
            VALUES (?, ?, ?, ?, ?, ?)""",
            (
                copied_session.world_id,
                copied_session.last_presented_event_sequence,
                copied_session.active_plan_id,
                copied_session.active_cue_index,
                copied_session.status,
                copied_session.updated_at,
            ),
        )
        self._save_idempotency(connection, request_id, target.id, result)
        self._insert_outbox(
            connection,
            event_id=f"outbox:world-copied:{target.id}",
            world_id=target.id,
            event_type="WorldCopied",
            payload=result,
        )
        return result

    @staticmethod
    def _copy_presentation_session(
        source: WorldPresentationSession | None,
        target_world_id: str,
        anchor_sequence: int,
        source_events: Sequence[TimelineEvent],
        target_events: Sequence[TimelineEvent],
        barriers: Sequence[DecisionBarrier],
    ) -> WorldPresentationSession:
        """Clamp and remap a derived presentation cursor to the copied prefix."""

        source_missing = source is None
        source = source or WorldPresentationSession(world_id=target_world_id)
        use_anchor_baseline = (
            source_missing
            or source.last_presented_event_sequence == 0
            and source.active_plan_id is None
            and source.status == "playing"
        )
        active_plan_id = None
        active_cue_index = 0
        if source.active_plan_id and not use_anchor_baseline:
            source_event = next(
                (
                    event
                    for event in source_events
                    if event.sequence <= anchor_sequence
                    and presentation_mode_for_event(event) == "scene"
                    and compile_performance_plan(event).id == source.active_plan_id
                ),
                None,
            )
            if source_event is not None:
                target_event = next(
                    event
                    for event in target_events
                    if event.sequence == source_event.sequence
                )
                active_plan_id = compile_performance_plan(target_event).id
                active_cue_index = source.active_cue_index
        last_presented = (
            anchor_sequence
            if use_anchor_baseline
            else min(source.last_presented_event_sequence, anchor_sequence)
        )
        has_unpresented_scene = any(
            event.sequence > last_presented
            and event.sequence <= anchor_sequence
            and presentation_mode_for_event(event) == "scene"
            for event in target_events
        )
        if source.status == "paused":
            status = "paused"
        elif active_plan_id or has_unpresented_scene:
            status = "playing"
        elif any(item.status == "pending" for item in barriers):
            status = "awaiting_barrier"
        else:
            status = "awaiting_action"
        return replace(
            source,
            world_id=target_world_id,
            last_presented_event_sequence=last_presented,
            active_plan_id=active_plan_id,
            active_cue_index=active_cue_index,
            status=status,
        )

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
