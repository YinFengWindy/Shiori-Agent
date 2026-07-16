"""SQLite serialization codecs for Coding Agent domain records."""

from __future__ import annotations

import json
import sqlite3
from typing import Any

from .models import (
    ApprovalRequest,
    ApprovalStatus,
    ApprovalType,
    CodingRepository,
    CodingTask,
    CodingTaskEvent,
    CodingTaskRun,
    CodingTaskStatus,
    CodingWorkspace,
    PermissionLevel,
    PlanSnapshot,
    Provider,
    RunStatus,
    TaskMode,
    WorkspaceStatus,
)


def dump_json(value: object) -> str:
    """Serialize a JSON value deterministically without escaping visible text."""

    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _load_json(value: str) -> Any:
    return json.loads(value)


def row_to_task(row: sqlite3.Row) -> CodingTask:
    return CodingTask(
        id=row["id"],
        request_id=row["request_id"],
        delivery_key=row["delivery_key"],
        manager_role_id=row["manager_role_id"],
        thread_id=row["thread_id"],
        source_channel=row["source_channel"],
        source_chat_id=row["source_chat_id"],
        repository_id=row["repository_id"],
        mode=TaskMode(row["mode"]),
        title=row["title"],
        request_text=row["request_text"],
        plan_snapshot_id=row["plan_snapshot_id"],
        status=CodingTaskStatus(row["status"]),
        room_id=row["room_id"],
        requester_id=row["requester_id"],
        assignee_role_id=row["assignee_role_id"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def row_to_run(row: sqlite3.Row) -> CodingTaskRun:
    return CodingTaskRun(
        id=row["id"],
        task_id=row["task_id"],
        parent_run_id=row["parent_run_id"],
        depends_on_run_ids=tuple(_load_json(row["depends_on_run_ids_json"])),
        attempt=int(row["attempt"]),
        provider=Provider(row["provider"]),
        profile_id=row["profile_id"],
        model=row["model"],
        effort=row["effort"],
        permission_level=PermissionLevel(row["permission_level"]),
        status=RunStatus(row["status"]),
        workspace_id=row["workspace_id"],
        worktree_path=row["worktree_path"],
        baseline_commit=row["baseline_commit"],
        branch_name=row["branch_name"],
        cli_version=row["cli_version"],
        cli_session_id=row["cli_session_id"],
        timeout_seconds=int(row["timeout_seconds"]),
        max_budget_usd=(
            float(row["max_budget_usd"])
            if row["max_budget_usd"] is not None
            else None
        ),
        started_at=row["started_at"],
        finished_at=row["finished_at"],
        result_summary=row["result_summary"],
        error_code=row["error_code"],
        error_message=row["error_message"],
        created_at=row["created_at"],
    )


def row_to_event(row: sqlite3.Row) -> CodingTaskEvent:
    return CodingTaskEvent(
        id=row["id"],
        task_id=row["task_id"],
        run_id=row["run_id"],
        sequence=int(row["sequence"]),
        event_type=row["event_type"],
        previous_status=row["previous_status"],
        next_status=row["next_status"],
        request_id=row["request_id"],
        payload=dict(_load_json(row["payload_json"])),
        created_at=row["created_at"],
    )


def row_to_plan_snapshot(row: sqlite3.Row) -> PlanSnapshot:
    return PlanSnapshot(
        id=row["id"],
        task_id=row["task_id"],
        version=int(row["version"]),
        content=row["content"],
        source_run_ids=tuple(_load_json(row["source_run_ids_json"])),
        confirmed_by=row["confirmed_by"],
        confirmed_at=row["confirmed_at"],
    )


def row_to_approval(row: sqlite3.Row) -> ApprovalRequest:
    return ApprovalRequest(
        id=row["id"],
        task_id=row["task_id"],
        run_id=row["run_id"],
        approval_type=ApprovalType(row["approval_type"]),
        requested_scope=dict(_load_json(row["requested_scope_json"])),
        reason=row["reason"],
        status=ApprovalStatus(row["status"]),
        expires_at=row["expires_at"],
        decided_at=row["decided_at"],
        decision_source=row["decision_source"],
        created_at=row["created_at"],
    )


def row_to_repository(row: sqlite3.Row) -> CodingRepository:
    return CodingRepository(
        id=row["id"],
        name=row["name"],
        root_path=row["root_path"],
        trusted=bool(row["trusted"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def row_to_workspace(row: sqlite3.Row) -> CodingWorkspace:
    return CodingWorkspace(
        id=row["id"],
        run_id=row["run_id"],
        repository_id=row["repository_id"],
        worktree_path=row["worktree_path"],
        baseline_commit=row["baseline_commit"],
        branch_name=row["branch_name"],
        status=WorkspaceStatus(row["status"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )
