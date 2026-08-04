"""Transactional SQLite repository for one Story database."""

from __future__ import annotations

import hashlib
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator
from uuid import uuid4

from ._json import dump, load
from ._schema import SCHEMA
from .errors import (
    StoryInvalidStateError,
    StoryNotFoundError,
    StoryRevisionConflictError,
    StoryTurnBusyError,
)
from .models import (
    DirectorDraft,
    PresentationCue,
    StoryBeat,
    StoryContext,
    StoryPlayerProfile,
    StoryResource,
    StoryResourceKind,
    utc_now,
)
from .schema_migrations import migrate_story_resources, migrate_story_timeline
from .story_time import next_story_clock, normalize_story_date, normalize_story_time_band


class StoryRepository:
    """Own durable Story facts, turns, attempts, cues, idempotency, and outbox."""

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
            migrate_story_timeline(self._connection)
            migrate_story_resources(self._connection)

    def close(self) -> None:
        """Close this Story database connection."""

        with self._lock:
            self._connection.close()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """Serialize one immediate transaction and roll back on failure."""

        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                yield self._connection
            except BaseException:
                self._connection.rollback()
                raise
            else:
                self._connection.commit()

    def create_story(
        self,
        *,
        story_id: str,
        title: str,
        background: str,
        role_snapshot: dict[str, Any],
        player_profile: StoryPlayerProfile,
        story_date: str,
        time_band: str,
        opening_context: dict[str, Any],
    ) -> dict[str, Any]:
        """Create the Story and its first awaiting-opening segment atomically."""

        player_profile.validate()
        if not title.strip():
            raise ValueError("title 不能为空")
        if not background.strip():
            raise ValueError("background 不能为空")
        normalized_story_date = normalize_story_date(story_date)
        normalized_time_band = normalize_story_time_band(time_band)
        segment_id = f"segment-{uuid4().hex}"
        now = utc_now()
        with self.transaction() as connection:
            connection.execute(
                """INSERT INTO stories
                VALUES (?, ?, ?, ?, ?, 'active', 0, ?)""",
                (
                    story_id,
                    title.strip(),
                    background,
                    dump(role_snapshot),
                    dump(player_profile.to_dict()),
                    now,
                ),
            )
            connection.execute(
                """INSERT INTO segments
                (id, story_id, sequence, story_date, time_band, status, mode,
                 operation, opening_context, runtime_snapshot)
                VALUES (?, ?, 1, ?, ?, 'awaiting_opening', 'plot', 'idle', ?, ?)""",
                (
                    segment_id,
                    story_id,
                    normalized_story_date,
                    normalized_time_band,
                    dump(opening_context),
                    dump({}),
                ),
            )
            resource_id = f"resource-{uuid4().hex}"
            connection.execute(
                """INSERT INTO story_resources
                VALUES (?, ?, 'background', 'generating', NULL, '', NULL, 1, NULL, ?, ?)""",
                (resource_id, story_id, now, now),
            )
        return self.story_read_model(story_id)

    def story_read_model(self, story_id: str) -> dict[str, Any]:
        """Build a renderer-safe Story read model from committed data."""

        with self._lock:
            story = self._require_row("SELECT * FROM stories WHERE id = ?", (story_id,))
            segment = self._require_row(
                "SELECT * FROM segments WHERE story_id = ? ORDER BY sequence DESC LIMIT 1",
                (story_id,),
            )
            beats = self._connection.execute(
                "SELECT * FROM beats WHERE story_id = ? ORDER BY sequence", (story_id,)
            ).fetchall()
            cues = self._connection.execute(
                """SELECT cues.payload FROM cues
                JOIN beats ON beats.id = cues.beat_id
                WHERE beats.story_id = ? ORDER BY beats.sequence""",
                (story_id,),
            ).fetchall()
            turns = self._connection.execute(
                """SELECT id, kind, input_text, status, active_attempt_id,
                committed_beat_ids, error, created_at, updated_at
                FROM turns WHERE story_id = ? ORDER BY created_at, id""",
                (story_id,),
            ).fetchall()
            resources = self._connection.execute(
                """SELECT * FROM story_resources
                WHERE story_id = ? ORDER BY sequence, created_at, id""",
                (story_id,),
            ).fetchall()
        resource_models = [self._resource_dict(row) for row in resources]
        background_resource = next(
            (resource for resource in resource_models if resource["kind"] == "background"),
            None,
        )
        return {
            "id": story["id"],
            "title": story["title"],
            "background": story["background"],
            "status": story["status"],
            "revision": int(story["revision"]),
            "roleSnapshot": load(story["role_snapshot"], {}),
            "playerProfile": load(story["player_profile"], {}),
            "segment": self._segment_dict(segment),
            "beats": [self._beat_dict(row) for row in beats],
            "cues": [load(row["payload"], {}) for row in cues],
            "turns": [self._turn_dict(row) for row in turns],
            "backgroundResource": background_resource,
            "cgGallery": resource_models,
            "currentStoryDate": str(segment["story_date"]),
            "currentTimeBand": str(segment["time_band"]),
        }

    def story_resources(self, story_id: str) -> list[dict[str, Any]]:
        """Return the Story-owned visual resources in creation order."""

        with self._lock:
            self._require_row("SELECT id FROM stories WHERE id = ?", (story_id,))
            rows = self._connection.execute(
                """SELECT * FROM story_resources
                WHERE story_id = ? ORDER BY sequence, created_at, id""",
                (story_id,),
            ).fetchall()
        return [self._resource_dict(row) for row in rows]

    def create_resource(
        self,
        story_id: str,
        *,
        kind: StoryResourceKind,
        prompt: str,
        source_turn_id: str | None,
    ) -> dict[str, Any]:
        """Create one asynchronous Story visual resource for a committed turn."""

        clean_prompt = prompt.strip()
        if not clean_prompt:
            raise ValueError("资源提示词不能为空")
        with self.transaction() as connection:
            self._require_row("SELECT id FROM stories WHERE id = ?", (story_id,), connection)
            sequence = int(
                connection.execute(
                    "SELECT COALESCE(MAX(sequence), 0) + 1 FROM story_resources WHERE story_id = ?",
                    (story_id,),
                ).fetchone()[0]
            )
            now = utc_now()
            resource_id = f"resource-{uuid4().hex}"
            connection.execute(
                """INSERT INTO story_resources
                VALUES (?, ?, ?, 'generating', NULL, ?, ?, ?, NULL, ?, ?)""",
                (resource_id, story_id, kind, clean_prompt, source_turn_id, sequence, now, now),
            )
            row = self._require_row(
                "SELECT * FROM story_resources WHERE id = ?", (resource_id,), connection
            )
        return self._resource_dict(row)

    def resource(self, resource_id: str) -> dict[str, Any]:
        """Return one Story-owned resource by its stable identifier."""

        with self._lock:
            row = self._require_row(
                "SELECT * FROM story_resources WHERE id = ?", (resource_id,)
            )
        return self._resource_dict(row)

    def prepare_resource(
        self,
        resource_id: str,
        *,
        prompt: str,
        source_turn_id: str | None,
    ) -> dict[str, Any]:
        """Attach the immutable generation inputs before a resource request."""

        clean_prompt = prompt.strip()
        with self.transaction() as connection:
            self._require_row(
                "SELECT * FROM story_resources WHERE id = ?", (resource_id,), connection
            )
            now = utc_now()
            connection.execute(
                """UPDATE story_resources
                SET prompt = ?, source_turn_id = ?, status = 'generating',
                    path = NULL, error_code = NULL, updated_at = ?
                WHERE id = ?""",
                (clean_prompt, source_turn_id, now, resource_id),
            )
            row = self._require_row(
                "SELECT * FROM story_resources WHERE id = ?", (resource_id,), connection
            )
        return self._resource_dict(row)

    def complete_resource(self, resource_id: str, path: str) -> dict[str, Any]:
        """Persist a successfully generated local asset path."""

        clean_path = path.strip()
        if not clean_path:
            raise ValueError("资源路径不能为空")
        with self.transaction() as connection:
            self._require_row(
                "SELECT * FROM story_resources WHERE id = ?", (resource_id,), connection
            )
            now = utc_now()
            connection.execute(
                """UPDATE story_resources
                SET status = 'ready', path = ?, error_code = NULL, updated_at = ?
                WHERE id = ?""",
                (clean_path, now, resource_id),
            )
            row = self._require_row(
                "SELECT * FROM story_resources WHERE id = ?", (resource_id,), connection
            )
        return self._resource_dict(row)

    def fail_resource(self, resource_id: str, error_code: str) -> dict[str, Any]:
        """Persist a safe, stable failure state without exposing provider details."""

        clean_code = error_code.strip() or "resource_generation_failed"
        with self.transaction() as connection:
            self._require_row(
                "SELECT * FROM story_resources WHERE id = ?", (resource_id,), connection
            )
            now = utc_now()
            connection.execute(
                """UPDATE story_resources
                SET status = 'failed', error_code = ?, updated_at = ?
                WHERE id = ?""",
                (clean_code, now, resource_id),
            )
            row = self._require_row(
                "SELECT * FROM story_resources WHERE id = ?", (resource_id,), connection
            )
        return self._resource_dict(row)

    def current_time_band(self, story_id: str) -> str:
        """Return the current player-facing Story period."""

        with self._lock:
            segment = self._require_row(
                "SELECT time_band FROM segments WHERE story_id = ? ORDER BY sequence DESC LIMIT 1",
                (story_id,),
            )
        return str(segment["time_band"])

    def current_story_date(self, story_id: str) -> str:
        """Return the current in-story calendar date without using system time."""

        with self._lock:
            segment = self._require_row(
                "SELECT story_date FROM segments WHERE story_id = ? ORDER BY sequence DESC LIMIT 1",
                (story_id,),
            )
        return str(segment["story_date"])

    def story_id_for_turn(self, turn_id: str) -> str:
        """Resolve a persisted Turn owner without loading unrelated Story state."""

        with self._lock:
            row = self._require_row(
                "SELECT story_id FROM turns WHERE id = ?", (turn_id,)
            )
        return str(row["story_id"])

    def opening_turn(self, story_id: str) -> dict[str, Any]:
        """Return the single durable opening receipt for a Story creation replay."""

        with self._lock:
            row = self._require_row(
                """SELECT * FROM turns WHERE story_id = ? AND kind = 'opening'
                ORDER BY created_at, id LIMIT 1""",
                (story_id,),
            )
        return self._turn_dict(row)

    def reset_interrupted_turn(self, turn_id: str) -> dict[str, Any]:
        """Return an interrupted generation Turn to pending for process recovery."""

        with self.transaction() as connection:
            turn = self._require_row("SELECT * FROM turns WHERE id = ?", (turn_id,), connection)
            if turn["status"] not in {"generating", "validating"}:
                return self._turn_dict(turn)
            now = utc_now()
            attempt_id = turn["active_attempt_id"]
            if attempt_id:
                connection.execute(
                    """UPDATE attempts SET status = 'failed', failure_category = ?, ended_at = ?
                    WHERE id = ?""",
                    ("generation_interrupted", now, attempt_id),
                )
            connection.execute(
                """UPDATE turns SET status = 'pending', active_attempt_id = NULL,
                error = NULL, updated_at = ? WHERE id = ?""",
                (now, turn_id),
            )
            connection.execute(
                "UPDATE segments SET operation = 'generating' WHERE id = ?",
                (turn["segment_id"],),
            )
            return self._turn_dict(
                self._require_row("SELECT * FROM turns WHERE id = ?", (turn_id,), connection)
            )

    def create_turn(
        self,
        *,
        story_id: str,
        input_text: str,
        request_id: str,
        request_payload_hash: str,
        expected_revision: int,
        kind: str = "player",
    ) -> dict[str, Any]:
        """Persist a player input before any Director call begins."""

        clean_input = input_text.strip()
        if kind not in {"opening", "player", "continue"}:
            raise ValueError("Turn kind 无效")
        if kind != "opening" and not clean_input:
            raise ValueError("input 不能为空")
        with self.transaction() as connection:
            story = self._require_row(
                "SELECT * FROM stories WHERE id = ?", (story_id,), connection
            )
            existing = connection.execute(
                """SELECT turns.*, turn_requests.story_id AS request_story_id,
                turn_requests.payload_hash FROM turns
                JOIN turn_requests ON turn_requests.turn_id = turns.id
                WHERE turns.request_id = ?""",
                (request_id,),
            ).fetchone()
            if existing is not None:
                if (
                    existing["request_story_id"] != story_id
                    or existing["payload_hash"] != request_payload_hash
                    or existing["input_text"] != clean_input
                    or existing["kind"] != kind
                ):
                    raise ValueError("request_id 携带了不同的请求")
                return self._turn_dict(existing)
            self._assert_revision(story, expected_revision)
            segment = self._require_row(
                """SELECT * FROM segments WHERE story_id = ?
                ORDER BY sequence DESC LIMIT 1""",
                (story_id,),
                connection,
            )
            if segment["status"] != "active" and segment["status"] != "awaiting_opening":
                raise StoryInvalidStateError("Story 段当前不可输入")
            busy = connection.execute(
                """SELECT id FROM turns WHERE segment_id = ?
                AND status IN ('pending', 'generating', 'validating')""",
                (segment["id"],),
            ).fetchone()
            if busy is not None:
                raise StoryTurnBusyError("Story 当前已有生成中的输入")
            turn_id = f"turn-{uuid4().hex}"
            now = utc_now()
            connection.execute(
                """INSERT INTO turns
                VALUES (?, ?, ?, ?, ?, ?, 'pending', NULL, '[]', NULL, ?, ?)""",
                (
                    turn_id,
                    story_id,
                    segment["id"],
                    request_id,
                    kind,
                    clean_input,
                    now,
                    now,
                ),
            )
            connection.execute(
                "UPDATE segments SET operation = 'generating' WHERE id = ?",
                (segment["id"],),
            )
            connection.execute(
                "INSERT INTO turn_requests VALUES (?, ?, ?, ?)",
                (request_id, story_id, request_payload_hash, turn_id),
            )
            return self._turn_dict(
                self._require_row("SELECT * FROM turns WHERE id = ?", (turn_id,), connection)
            )

    def start_attempt(self, turn_id: str) -> dict[str, Any]:
        """Move one pending Turn into an active generation attempt."""

        attempt_id = f"attempt-{uuid4().hex}"
        with self.transaction() as connection:
            turn = self._require_row("SELECT * FROM turns WHERE id = ?", (turn_id,), connection)
            if turn["status"] != "pending":
                raise StoryInvalidStateError("Turn 不处于可生成状态")
            now = utc_now()
            connection.execute(
                "INSERT INTO attempts VALUES (?, ?, 'running', NULL, ?, NULL)",
                (attempt_id, turn_id, now),
            )
            connection.execute(
                """UPDATE turns SET status = 'generating', active_attempt_id = ?, updated_at = ?
                WHERE id = ?""",
                (attempt_id, now, turn_id),
            )
        return {"turn_id": turn_id, "attempt_id": attempt_id}

    def mark_validating(self, turn_id: str, attempt_id: str) -> None:
        """Record that an active attempt entered continuity validation."""

        with self.transaction() as connection:
            self._assert_active_attempt(connection, turn_id, attempt_id)
            connection.execute(
                "UPDATE turns SET status = 'validating', updated_at = ? WHERE id = ?",
                (utc_now(), turn_id),
            )

    def commit_draft(
        self,
        *,
        turn_id: str,
        attempt_id: str,
        draft: DirectorDraft,
        default_time_band: str,
    ) -> tuple[list[tuple[StoryBeat, PresentationCue, dict[str, Any]]], dict[str, Any]]:
        """Atomically commit one validated Director draft and release the input lane."""

        with self.transaction() as connection:
            turn = self._assert_active_attempt(connection, turn_id, attempt_id)
            story = self._require_row(
                "SELECT * FROM stories WHERE id = ?", (turn["story_id"],), connection
            )
            next_sequence = int(
                connection.execute(
                    "SELECT COALESCE(MAX(sequence), 0) + 1 FROM beats WHERE story_id = ?",
                    (story["id"],),
                ).fetchone()[0]
            )
            recorded_at = utc_now()
            committed_ids = load(turn["committed_beat_ids"], [])
            revision = int(story["revision"])
            segment = self._require_row(
                "SELECT story_date, time_band FROM segments WHERE id = ?",
                (turn["segment_id"],),
                connection,
            )
            current_story_date = str(segment["story_date"])
            current_time_band = str(segment["time_band"] or default_time_band)
            committed: list[tuple[StoryBeat, PresentationCue, dict[str, Any]]] = []
            for offset, item in enumerate(draft.beats):
                beat_id = f"beat-{uuid4().hex}"
                cue_id = f"cue-{uuid4().hex}"
                story_date, time_band = next_story_clock(
                    current_story_date, current_time_band, item.time_band
                )
                current_story_date = story_date
                current_time_band = time_band
                beat = StoryBeat(
                    id=beat_id,
                    story_id=story["id"],
                    segment_id=turn["segment_id"],
                    turn_id=turn_id,
                    sequence=next_sequence + offset,
                    story_date=story_date,
                    time_band=time_band,
                    text=item.text,
                    kind=item.kind,
                    speaker=item.speaker,
                    recorded_at=recorded_at,
                )
                cue = PresentationCue(
                    id=cue_id,
                    beat_id=beat_id,
                    story_id=story["id"],
                    text=item.text,
                    kind=item.kind,
                    speaker=item.speaker,
                )
                connection.execute(
                    "INSERT INTO beats VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        beat.id,
                        beat.story_id,
                        beat.segment_id,
                        beat.turn_id,
                        beat.sequence,
                        dump(beat.to_dict()),
                        beat.recorded_at,
                    ),
                )
                connection.execute(
                    "INSERT INTO cues VALUES (?, ?, ?)",
                    (cue.id, beat.id, dump(cue.to_dict())),
                )
                committed_ids.append(beat.id)
                revision += 1
                event_id = f"event-{uuid4().hex}"
                payload = {
                    "event_id": event_id,
                    "event_type": "beat.committed",
                    "story_id": story["id"],
                    "segment_id": turn["segment_id"],
                    "story_revision": revision,
                    "beat": beat.to_dict(),
                    "cue": cue.to_dict(),
                }
                connection.execute(
                    "INSERT INTO outbox VALUES (NULL, ?, ?, ?, ?, ?)",
                    (event_id, story["id"], "beat.committed", dump(payload), recorded_at),
                )
                committed.append((beat, cue, payload))
            connection.execute(
                """UPDATE segments SET story_date = ?, time_band = ? WHERE id = ?""",
                (current_story_date, current_time_band, turn["segment_id"]),
            )
            connection.execute(
                """UPDATE stories SET revision = ? WHERE id = ?""",
                (revision, story["id"]),
            )
            connection.execute(
                """UPDATE attempts SET status = 'succeeded', ended_at = ? WHERE id = ?""",
                (recorded_at, attempt_id),
            )
            connection.execute(
                """UPDATE turns SET status = 'committed', active_attempt_id = NULL,
                committed_beat_ids = ?, updated_at = ?
                WHERE id = ?""",
                (dump(committed_ids), recorded_at, turn_id),
            )
            connection.execute(
                "UPDATE segments SET status = 'active', operation = 'awaiting_player' WHERE id = ?",
                (turn["segment_id"],),
            )
        return committed, self.story_read_model(turn["story_id"])

    def finish_turn(self, turn_id: str, attempt_id: str) -> dict[str, Any]:
        """Mark a successful attempt and release the segment input lane."""

        with self.transaction() as connection:
            turn = self._assert_active_attempt(connection, turn_id, attempt_id)
            now = utc_now()
            connection.execute(
                "UPDATE attempts SET status = 'succeeded', ended_at = ? WHERE id = ?",
                (now, attempt_id),
            )
            connection.execute(
                """UPDATE turns SET status = 'committed', active_attempt_id = NULL, updated_at = ?
                WHERE id = ?""",
                (now, turn_id),
            )
            connection.execute(
                """UPDATE segments SET status = 'active', operation = 'awaiting_player'
                WHERE id = ?""",
                (turn["segment_id"],),
            )
        return self.story_read_model(turn["story_id"])

    def fail_turn(
        self, turn_id: str, attempt_id: str, *, code: str, message: str
    ) -> dict[str, Any]:
        """Persist a failed attempt without touching Story facts."""

        with self.transaction() as connection:
            turn = self._assert_active_attempt(connection, turn_id, attempt_id)
            now = utc_now()
            connection.execute(
                """UPDATE attempts SET status = 'failed', failure_category = ?, ended_at = ?
                WHERE id = ?""",
                (code, now, attempt_id),
            )
            connection.execute(
                """UPDATE turns SET status = 'failed', active_attempt_id = NULL,
                error = ?, updated_at = ? WHERE id = ?""",
                (dump({"code": code, "message": message}), now, turn_id),
            )
            connection.execute(
                "UPDATE segments SET status = 'active', operation = 'awaiting_player' WHERE id = ?",
                (turn["segment_id"],),
            )
        return self.story_read_model(turn["story_id"])

    def retry_attempt(
        self, turn_id: str, attempt_id: str, *, failure_category: str
    ) -> dict[str, Any]:
        """Close one transient attempt and start the single allowed replacement."""

        replacement_id = f"attempt-{uuid4().hex}"
        with self.transaction() as connection:
            self._assert_active_attempt(connection, turn_id, attempt_id)
            now = utc_now()
            connection.execute(
                """UPDATE attempts SET status = 'retrying', failure_category = ?, ended_at = ?
                WHERE id = ?""",
                (failure_category, now, attempt_id),
            )
            connection.execute(
                "INSERT INTO attempts VALUES (?, ?, 'running', NULL, ?, NULL)",
                (replacement_id, turn_id, now),
            )
            connection.execute(
                """UPDATE turns SET status = 'generating', active_attempt_id = ?, updated_at = ?
                WHERE id = ?""",
                (replacement_id, now, turn_id),
            )
        return {"turn_id": turn_id, "attempt_id": replacement_id}

    def cancel_turn(self, turn_id: str, attempt_id: str) -> dict[str, Any]:
        """Persist a cancelled in-flight attempt during service shutdown."""

        with self.transaction() as connection:
            turn = self._assert_active_attempt(connection, turn_id, attempt_id)
            now = utc_now()
            connection.execute(
                "UPDATE attempts SET status = 'cancelled', ended_at = ? WHERE id = ?",
                (now, attempt_id),
            )
            connection.execute(
                """UPDATE turns SET status = 'cancelled', active_attempt_id = NULL,
                error = ?, updated_at = ? WHERE id = ?""",
                (dump({"code": "cancelled", "message": "Story 生成已取消"}), now, turn_id),
            )
            connection.execute(
                "UPDATE segments SET status = 'active', operation = 'awaiting_player' WHERE id = ?",
                (turn["segment_id"],),
            )
        return self.story_read_model(turn["story_id"])

    def build_context(self, story_id: str) -> StoryContext:
        """Assemble the fixed opening state and rolling six-Turn window."""

        with self._lock:
            story = self._require_row("SELECT * FROM stories WHERE id = ?", (story_id,))
            segment = self._require_row(
                "SELECT * FROM segments WHERE story_id = ? ORDER BY sequence DESC LIMIT 1",
                (story_id,),
            )
            turns = self._connection.execute(
                """SELECT * FROM turns WHERE story_id = ? AND kind IN ('player', 'continue')
                AND status IN ('committed', 'failed', 'cancelled')
                ORDER BY created_at DESC, id DESC LIMIT 6""",
                (story_id,),
            ).fetchall()
            beats = self._connection.execute(
                "SELECT payload FROM beats WHERE story_id = ? ORDER BY sequence DESC LIMIT 12",
                (story_id,),
            ).fetchall()
        return StoryContext(
            story=dict(story),
            role_snapshot=load(story["role_snapshot"], {}),
            player_profile=load(story["player_profile"], {}),
            segment=self._segment_dict(segment),
            recent_turns=tuple(self._turn_dict(row) for row in reversed(turns)),
            recent_beats=tuple(load(row["payload"], {}) for row in reversed(beats)),
        )

    def _assert_active_attempt(
        self, connection: sqlite3.Connection, turn_id: str, attempt_id: str
    ) -> sqlite3.Row:
        turn = self._require_row("SELECT * FROM turns WHERE id = ?", (turn_id,), connection)
        if turn["active_attempt_id"] != attempt_id or turn["status"] not in {
            "generating",
            "validating",
        }:
            raise StoryInvalidStateError("生成 attempt 已失效")
        return turn

    @staticmethod
    def _assert_revision(story: sqlite3.Row, expected_revision: int) -> None:
        if int(story["revision"]) != int(expected_revision):
            raise StoryRevisionConflictError("Story revision 已变化")

    def _require_row(
        self,
        query: str,
        params: tuple[Any, ...],
        connection: sqlite3.Connection | None = None,
    ) -> sqlite3.Row:
        conn = connection or self._connection
        row = conn.execute(query, params).fetchone()
        if row is None:
            raise StoryNotFoundError("Story 记录不存在")
        return row

    @staticmethod
    def _segment_dict(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "sequence": int(row["sequence"]),
            "storyDate": row["story_date"],
            "timeBand": row["time_band"],
            "status": row["status"],
            "mode": row["mode"],
            "operation": row["operation"],
            "openingContext": load(row["opening_context"], {}),
            "runtimeSnapshot": load(row["runtime_snapshot"], {}),
        }

    @staticmethod
    def _turn_dict(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "kind": row["kind"],
            "input": row["input_text"],
            "status": row["status"],
            "attemptId": row["active_attempt_id"],
            "committedBeatIds": load(row["committed_beat_ids"], []),
            "error": load(row["error"], None) if row["error"] else None,
            "createdAt": row["created_at"],
            "updatedAt": row["updated_at"],
        }

    @staticmethod
    def _beat_dict(row: sqlite3.Row) -> dict[str, Any]:
        payload = load(row["payload"], {})
        return {
            "id": payload["id"],
            "storyId": payload["story_id"],
            "segmentId": payload["segment_id"],
            "turnId": payload["turn_id"],
            "sequence": int(payload["sequence"]),
            "storyDate": payload["story_date"],
            "timeBand": payload["time_band"],
            "text": payload["text"],
            "kind": payload["kind"],
            "speaker": payload.get("speaker"),
            "recordedAt": payload["recorded_at"],
        }

    @staticmethod
    def _resource_dict(row: sqlite3.Row) -> dict[str, Any]:
        resource = StoryResource(
            id=str(row["id"]),
            story_id=str(row["story_id"]),
            kind=str(row["kind"]),  # type: ignore[arg-type]
            status=str(row["status"]),  # type: ignore[arg-type]
            path=str(row["path"]) if row["path"] else None,
            prompt=str(row["prompt"] or ""),
            source_turn_id=(str(row["source_turn_id"]) if row["source_turn_id"] else None),
            sequence=int(row["sequence"]),
            error_code=str(row["error_code"]) if row["error_code"] else None,
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )
        return resource.to_dict()


def payload_hash(payload: dict[str, Any]) -> str:
    """Hash a bridge payload for request replay protection."""

    return hashlib.sha256(dump(payload).encode("utf-8")).hexdigest()
