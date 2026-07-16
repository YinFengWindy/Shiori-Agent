"""SQLite schema ownership for the Coding Agent data domain."""

from __future__ import annotations

import sqlite3


SCHEMA_VERSION = 1


def initialize_schema(connection: sqlite3.Connection) -> None:
    """Apply forward-only Coding Agent schema initialization transactionally."""

    current = int(connection.execute("PRAGMA user_version").fetchone()[0])
    if current > SCHEMA_VERSION:
        raise RuntimeError(
            f"coding agent schema {current} is newer than supported {SCHEMA_VERSION}"
        )
    if current == SCHEMA_VERSION:
        return
    try:
        connection.executescript(
            f"""
        BEGIN IMMEDIATE;
        CREATE TABLE IF NOT EXISTS coding_tasks (
            id TEXT PRIMARY KEY,
            request_id TEXT NOT NULL,
            delivery_key TEXT NOT NULL UNIQUE,
            manager_role_id TEXT NOT NULL,
            thread_id TEXT NOT NULL,
            source_channel TEXT NOT NULL,
            source_chat_id TEXT NOT NULL,
            repository_id TEXT NOT NULL,
            mode TEXT NOT NULL,
            title TEXT NOT NULL,
            request_text TEXT NOT NULL,
            plan_snapshot_id TEXT,
            status TEXT NOT NULL,
            room_id TEXT,
            requester_id TEXT,
            assignee_role_id TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS coding_task_runs (
            id TEXT PRIMARY KEY,
            task_id TEXT NOT NULL REFERENCES coding_tasks(id),
            parent_run_id TEXT REFERENCES coding_task_runs(id),
            depends_on_run_ids_json TEXT NOT NULL,
            attempt INTEGER NOT NULL,
            provider TEXT NOT NULL,
            profile_id TEXT NOT NULL,
            model TEXT NOT NULL,
            effort TEXT NOT NULL,
            permission_level TEXT NOT NULL,
            status TEXT NOT NULL,
            workspace_id TEXT,
            worktree_path TEXT,
            baseline_commit TEXT,
            branch_name TEXT,
            cli_version TEXT,
            cli_session_id TEXT,
            timeout_seconds INTEGER NOT NULL,
            max_budget_usd REAL,
            started_at TEXT,
            finished_at TEXT,
            result_summary TEXT,
            error_code TEXT,
            error_message TEXT,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS coding_task_events (
            id TEXT PRIMARY KEY,
            task_id TEXT NOT NULL REFERENCES coding_tasks(id),
            run_id TEXT REFERENCES coding_task_runs(id),
            sequence INTEGER NOT NULL,
            event_type TEXT NOT NULL,
            previous_status TEXT,
            next_status TEXT,
            request_id TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(task_id, sequence)
        );
        CREATE TABLE IF NOT EXISTS coding_plan_snapshots (
            id TEXT PRIMARY KEY,
            task_id TEXT NOT NULL REFERENCES coding_tasks(id),
            version INTEGER NOT NULL,
            content TEXT NOT NULL,
            source_run_ids_json TEXT NOT NULL,
            confirmed_by TEXT NOT NULL,
            confirmed_at TEXT NOT NULL,
            UNIQUE(task_id, version)
        );
        CREATE TABLE IF NOT EXISTS coding_approval_requests (
            id TEXT PRIMARY KEY,
            task_id TEXT NOT NULL REFERENCES coding_tasks(id),
            run_id TEXT REFERENCES coding_task_runs(id),
            approval_type TEXT NOT NULL,
            requested_scope_json TEXT NOT NULL,
            reason TEXT NOT NULL,
            status TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            decided_at TEXT,
            decision_source TEXT,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS coding_repositories (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            root_path TEXT NOT NULL UNIQUE,
            trusted INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS coding_workspaces (
            id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL UNIQUE REFERENCES coding_task_runs(id),
            repository_id TEXT NOT NULL,
            worktree_path TEXT NOT NULL UNIQUE,
            baseline_commit TEXT NOT NULL,
            branch_name TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS coding_artifacts (
            id TEXT PRIMARY KEY,
            task_id TEXT NOT NULL REFERENCES coding_tasks(id),
            run_id TEXT REFERENCES coding_task_runs(id),
            artifact_type TEXT NOT NULL,
            path TEXT,
            summary TEXT,
            metadata_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_coding_runs_task
            ON coding_task_runs(task_id, created_at);
        CREATE INDEX IF NOT EXISTS idx_coding_runs_recovery
            ON coding_task_runs(status, created_at);
        CREATE INDEX IF NOT EXISTS idx_coding_events_task_sequence
            ON coding_task_events(task_id, sequence);
        CREATE INDEX IF NOT EXISTS idx_coding_approvals_pending
            ON coding_approval_requests(status, expires_at);
        PRAGMA user_version = {SCHEMA_VERSION};
        COMMIT;
            """
        )
    except BaseException:
        if connection.in_transaction:
            connection.rollback()
        raise
