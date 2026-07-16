"""Versioned SQLite persistence for Coding Agent tasks and audit events."""

from __future__ import annotations

import sqlite3
import threading
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from .models import (
    CodingTask,
    CodingTaskEvent,
    CodingTaskRun,
    CodingTaskStatus,
    RunStatus,
    new_id,
    utc_now,
)
from .state_machine import derive_task_status, require_run_transition
from .store_approvals import CodingAgentRecordNotFound, StoreApprovalsMixin
from .store_plans import StorePlansMixin
from .store_resources import StoreResourcesMixin
from .store_rows import (
    dump_json,
    row_to_event,
    row_to_run,
    row_to_task,
)
from .store_schema import SCHEMA_VERSION, initialize_schema

_RUN_RESULT_FIELDS = frozenset(
    {
        "cli_version",
        "cli_session_id",
        "started_at",
        "finished_at",
        "result_summary",
        "error_code",
        "error_message",
    }
)


class CodingAgentStore(StoreResourcesMixin, StorePlansMixin, StoreApprovalsMixin):
    """Own the independent Coding Agent SQLite database and its transactions."""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        if str(db_path) != ":memory:":
            self.db_path.expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(
            str(db_path), timeout=30.0, check_same_thread=False, isolation_level=None
        )
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._connection.execute("PRAGMA busy_timeout = 30000")
        self._lock = threading.RLock()
        self._closed = False
        self._initialize_schema()

    @property
    def schema_version(self) -> int:
        """Return the schema version currently stored in SQLite."""

        with self._lock:
            row = self._connection.execute("PRAGMA user_version").fetchone()
            return int(row[0])

    def close(self) -> None:
        """Close the owned SQLite connection; repeated calls are harmless."""

        with self._lock:
            if self._closed:
                return
            self._closed = True
            self._connection.close()

    def __enter__(self) -> CodingAgentStore:
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def _initialize_schema(self) -> None:
        with self._lock:
            initialize_schema(self._connection)

    @contextmanager
    def _transaction(self) -> Iterator[None]:
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                yield
            except BaseException:
                self._connection.rollback()
                raise
            else:
                self._connection.commit()

    def create_task_with_run(
        self,
        task: CodingTask,
        run: CodingTaskRun,
        *,
        event_type: str = "run_queued",
        event_payload: Mapping[str, Any] | None = None,
    ) -> tuple[CodingTask, CodingTaskRun, bool]:
        """Atomically create a task, its initial run and queued audit event.

        A repeated delivery key returns the original task and first run without
        creating another event or external side effect.
        """

        if not task.delivery_key:
            raise ValueError("delivery_key must not be empty")
        if run.task_id != task.id:
            raise ValueError("run.task_id must match task.id")
        if task.status is not CodingTaskStatus.QUEUED or run.status is not RunStatus.QUEUED:
            raise ValueError("new tasks and runs must start queued")
        try:
            with self._transaction():
                existing = self._get_task_by_delivery_key_locked(task.delivery_key)
                if existing is not None:
                    return existing, self._get_first_run_locked(existing.id), False
                self._insert_task_locked(task)
                self._insert_run_locked(run)
                self._append_event_locked(
                    task_id=task.id,
                    run_id=run.id,
                    event_type=event_type,
                    request_id=task.request_id,
                    previous_status=None,
                    next_status=RunStatus.QUEUED,
                    payload=event_payload,
                )
            return task, run, True
        except sqlite3.IntegrityError:
            existing = self.get_task_by_delivery_key(task.delivery_key)
            if existing is None:
                raise
            return existing, self._get_first_run(existing.id), False

    def get_task(self, task_id: str) -> CodingTask | None:
        """Return a task by ID, or `None` when absent."""

        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM coding_tasks WHERE id = ?", (task_id,)
            ).fetchone()
            return row_to_task(row) if row else None

    def list_tasks(
        self,
        *,
        manager_role_id: str | None = None,
        thread_id: str | None = None,
    ) -> list[CodingTask]:
        """List tasks with optional role and conversation ownership filters."""

        clauses: list[str] = []
        values: list[str] = []
        if manager_role_id is not None:
            clauses.append("manager_role_id = ?")
            values.append(manager_role_id)
        if thread_id is not None:
            clauses.append("thread_id = ?")
            values.append(thread_id)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._lock:
            rows = self._connection.execute(
                f"SELECT * FROM coding_tasks{where} ORDER BY created_at, id", values
            ).fetchall()
            return [row_to_task(row) for row in rows]

    def get_task_by_delivery_key(self, delivery_key: str) -> CodingTask | None:
        """Return the task that owns an idempotent delivery key."""

        with self._lock:
            return self._get_task_by_delivery_key_locked(delivery_key)

    def _get_task_by_delivery_key_locked(self, delivery_key: str) -> CodingTask | None:
        row = self._connection.execute(
            "SELECT * FROM coding_tasks WHERE delivery_key = ?", (delivery_key,)
        ).fetchone()
        return row_to_task(row) if row else None

    def get_run(self, run_id: str) -> CodingTaskRun | None:
        """Return a run by ID, or `None` when absent."""

        with self._lock:
            row = self._connection.execute(
                "SELECT * FROM coding_task_runs WHERE id = ?", (run_id,)
            ).fetchone()
            return row_to_run(row) if row else None

    def create_run(
        self,
        run: CodingTaskRun,
        *,
        request_id: str,
        event_payload: Mapping[str, Any] | None = None,
    ) -> CodingTaskRun:
        """Atomically append a queued parallel or retry run to an existing task."""

        if run.status is not RunStatus.QUEUED:
            raise ValueError("new runs must start queued")
        with self._transaction():
            if self._get_task_locked(run.task_id) is None:
                raise CodingAgentRecordNotFound(f"task not found: {run.task_id}")
            related_run_ids = tuple(run.depends_on_run_ids) + (
                (run.parent_run_id,) if run.parent_run_id else ()
            )
            for related_run_id in related_run_ids:
                related = self._require_run_locked(related_run_id)
                if related.task_id != run.task_id:
                    raise ValueError("Run 依赖和 parent_run_id 必须属于同一 Task")
            self._insert_run_locked(run)
            self._append_event_locked(
                task_id=run.task_id,
                run_id=run.id,
                event_type="run_queued",
                request_id=request_id,
                previous_status=None,
                next_status=RunStatus.QUEUED,
                payload=event_payload,
            )
            self._refresh_task_status_locked(run.task_id)
            return run

    def list_runs(
        self,
        *,
        task_id: str | None = None,
        manager_role_id: str | None = None,
        thread_id: str | None = None,
    ) -> list[CodingTaskRun]:
        """List runs with optional task, owner-role and conversation filters."""

        clauses: list[str] = []
        values: list[str] = []
        if task_id is not None:
            clauses.append("r.task_id = ?")
            values.append(task_id)
        if manager_role_id is not None:
            clauses.append("t.manager_role_id = ?")
            values.append(manager_role_id)
        if thread_id is not None:
            clauses.append("t.thread_id = ?")
            values.append(thread_id)
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._lock:
            rows = self._connection.execute(
                "SELECT r.* FROM coding_task_runs r "
                "JOIN coding_tasks t ON t.id = r.task_id"
                f"{where} ORDER BY r.created_at, r.id",
                values,
            ).fetchall()
            return [row_to_run(row) for row in rows]

    def list_recoverable_runs(self) -> list[CodingTaskRun]:
        """Return all non-terminal runs that startup recovery must inspect."""

        placeholders = ", ".join("?" for _ in range(3))
        statuses = (
            RunStatus.QUEUED,
            RunStatus.RUNNING,
            RunStatus.WAITING_APPROVAL,
        )
        with self._lock:
            rows = self._connection.execute(
                f"SELECT * FROM coding_task_runs WHERE status IN ({placeholders}) "
                "ORDER BY created_at, id",
                statuses,
            ).fetchall()
            return [row_to_run(row) for row in rows]

    def update_run_workspace(
        self,
        run_id: str,
        *,
        workspace_id: str,
        worktree_path: str,
        baseline_commit: str,
        branch_name: str,
    ) -> CodingTaskRun:
        """Persist the validated managed-worktree mapping for a queued run."""

        with self._transaction():
            if self._get_run_locked(run_id) is None:
                raise CodingAgentRecordNotFound(f"run not found: {run_id}")
            self._connection.execute(
                """UPDATE coding_task_runs
                   SET workspace_id = ?, worktree_path = ?, baseline_commit = ?, branch_name = ?
                   WHERE id = ?""",
                (workspace_id, worktree_path, baseline_commit, branch_name, run_id),
            )
            return self._require_run_locked(run_id)

    def update_run_session(self, run_id: str, cli_session_id: str) -> CodingTaskRun:
        """Persist an explicit provider session ID as soon as streaming reveals it."""

        session_id = cli_session_id.strip()
        if not session_id:
            raise ValueError("cli_session_id must not be empty")
        with self._transaction():
            if self._get_run_locked(run_id) is None:
                raise CodingAgentRecordNotFound(f"run not found: {run_id}")
            self._connection.execute(
                "UPDATE coding_task_runs SET cli_session_id = ? WHERE id = ?",
                (session_id, run_id),
            )
            return self._require_run_locked(run_id)

    def transition_run(
        self,
        run_id: str,
        next_status: RunStatus,
        *,
        event_type: str,
        request_id: str,
        payload: Mapping[str, Any] | None = None,
        **result_fields: str | None,
    ) -> CodingTaskRun:
        """Atomically transition a run, append its event and refresh its task."""

        unknown = set(result_fields) - _RUN_RESULT_FIELDS
        if unknown:
            raise ValueError(f"unsupported run result fields: {sorted(unknown)}")
        with self._transaction():
            current = self._require_run_locked(run_id)
            if current.status is next_status:
                return current
            require_run_transition(current.status, next_status)
            updates: dict[str, str | None] = dict(result_fields)
            if next_status is RunStatus.RUNNING and "started_at" not in updates:
                updates["started_at"] = utc_now()
            if next_status in {
                RunStatus.SUCCEEDED,
                RunStatus.FAILED,
                RunStatus.CANCELLED,
            } and "finished_at" not in updates:
                updates["finished_at"] = utc_now()
            assignments = ["status = ?", *(f"{name} = ?" for name in updates)]
            values: list[str | None] = [next_status, *updates.values(), run_id]
            self._connection.execute(
                f"UPDATE coding_task_runs SET {', '.join(assignments)} WHERE id = ?",
                values,
            )
            self._append_event_locked(
                task_id=current.task_id,
                run_id=run_id,
                event_type=event_type,
                request_id=request_id,
                previous_status=current.status,
                next_status=next_status,
                payload=payload,
            )
            self._refresh_task_status_locked(current.task_id)
            return self._require_run_locked(run_id)

    def append_event(
        self,
        *,
        task_id: str,
        event_type: str,
        request_id: str,
        run_id: str | None = None,
        payload: Mapping[str, Any] | None = None,
    ) -> CodingTaskEvent:
        """Append a non-state audit event with the next task sequence."""

        with self._transaction():
            if self._get_task_locked(task_id) is None:
                raise CodingAgentRecordNotFound(f"task not found: {task_id}")
            return self._append_event_locked(
                task_id=task_id,
                run_id=run_id,
                event_type=event_type,
                request_id=request_id,
                previous_status=None,
                next_status=None,
                payload=payload,
            )

    def list_events(self, task_id: str, *, after_sequence: int = 0) -> list[CodingTaskEvent]:
        """List a task's events in replay order after an optional cursor."""

        with self._lock:
            rows = self._connection.execute(
                """SELECT * FROM coding_task_events
                   WHERE task_id = ? AND sequence > ? ORDER BY sequence""",
                (task_id, after_sequence),
            ).fetchall()
            return [row_to_event(row) for row in rows]

    def _insert_task_locked(self, task: CodingTask) -> None:
        self._connection.execute(
            """INSERT INTO coding_tasks
               (id, request_id, delivery_key, manager_role_id, thread_id,
                source_channel, source_chat_id, repository_id, mode, title,
                request_text, plan_snapshot_id, status, room_id, requester_id,
                assignee_role_id, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                task.id,
                task.request_id,
                task.delivery_key,
                task.manager_role_id,
                task.thread_id,
                task.source_channel,
                task.source_chat_id,
                task.repository_id,
                task.mode,
                task.title,
                task.request_text,
                task.plan_snapshot_id,
                task.status,
                task.room_id,
                task.requester_id,
                task.assignee_role_id,
                task.created_at,
                task.updated_at,
            ),
        )

    def _insert_run_locked(self, run: CodingTaskRun) -> None:
        self._connection.execute(
            """INSERT INTO coding_task_runs
               (id, task_id, parent_run_id, depends_on_run_ids_json, attempt,
                provider, profile_id, model, effort, permission_level, status,
                workspace_id, worktree_path, baseline_commit, branch_name,
                cli_version, cli_session_id, timeout_seconds, max_budget_usd,
                started_at, finished_at, result_summary, error_code, error_message,
                created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                       ?, ?, ?, ?, ?, ?, ?)""",
            (
                run.id,
                run.task_id,
                run.parent_run_id,
                dump_json(run.depends_on_run_ids),
                run.attempt,
                run.provider,
                run.profile_id,
                run.model,
                run.effort,
                run.permission_level,
                run.status,
                run.workspace_id,
                run.worktree_path,
                run.baseline_commit,
                run.branch_name,
                run.cli_version,
                run.cli_session_id,
                run.timeout_seconds,
                run.max_budget_usd,
                run.started_at,
                run.finished_at,
                run.result_summary,
                run.error_code,
                run.error_message,
                run.created_at,
            ),
        )

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
    ) -> CodingTaskEvent:
        row = self._connection.execute(
            """SELECT COALESCE(MAX(sequence), 0) + 1 AS next_sequence
               FROM coding_task_events WHERE task_id = ?""",
            (task_id,),
        ).fetchone()
        event = CodingTaskEvent(
            id=new_id(),
            task_id=task_id,
            run_id=run_id,
            sequence=int(row["next_sequence"]),
            event_type=event_type,
            previous_status=str(previous_status) if previous_status is not None else None,
            next_status=str(next_status) if next_status is not None else None,
            request_id=request_id,
            payload=dict(payload or {}),
        )
        self._connection.execute(
            """INSERT INTO coding_task_events
               (id, task_id, run_id, sequence, event_type, previous_status,
                next_status, request_id, payload_json, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                event.id,
                event.task_id,
                event.run_id,
                event.sequence,
                event.event_type,
                event.previous_status,
                event.next_status,
                event.request_id,
                dump_json(event.payload),
                event.created_at,
            ),
        )
        return event

    def _refresh_task_status_locked(self, task_id: str) -> None:
        rows = self._connection.execute(
            "SELECT status FROM coding_task_runs WHERE task_id = ?", (task_id,)
        ).fetchall()
        status = derive_task_status(RunStatus(row["status"]) for row in rows)
        self._connection.execute(
            "UPDATE coding_tasks SET status = ?, updated_at = ? WHERE id = ?",
            (status, utc_now(), task_id),
        )

    def _get_task_locked(self, task_id: str) -> CodingTask | None:
        row = self._connection.execute(
            "SELECT * FROM coding_tasks WHERE id = ?", (task_id,)
        ).fetchone()
        return row_to_task(row) if row else None

    def _get_run_locked(self, run_id: str) -> CodingTaskRun | None:
        row = self._connection.execute(
            "SELECT * FROM coding_task_runs WHERE id = ?", (run_id,)
        ).fetchone()
        return row_to_run(row) if row else None

    def _require_run_locked(self, run_id: str) -> CodingTaskRun:
        run = self._get_run_locked(run_id)
        if run is None:
            raise CodingAgentRecordNotFound(f"run not found: {run_id}")
        return run

    def _get_first_run_locked(self, task_id: str) -> CodingTaskRun:
        row = self._connection.execute(
            """SELECT * FROM coding_task_runs WHERE task_id = ?
               ORDER BY created_at, id LIMIT 1""",
            (task_id,),
        ).fetchone()
        if row is None:
            raise CodingAgentRecordNotFound(f"task has no run: {task_id}")
        return row_to_run(row)

    def _get_first_run(self, task_id: str) -> CodingTaskRun:
        with self._lock:
            return self._get_first_run_locked(task_id)

    # Explicit domain aliases keep integrations independent of table-oriented names.
    create_coding_task_with_run = create_task_with_run
    get_coding_task = get_task
    list_coding_tasks = list_tasks
    get_coding_task_by_delivery_key = get_task_by_delivery_key
    create_coding_run = create_run
    get_coding_run = get_run
    list_coding_runs = list_runs
    transition_coding_run = transition_run
    append_coding_event = append_event
    list_coding_events = list_events
