"""Immutable domain records for persisted Coding Agent work."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from uuid import uuid4


def new_id() -> str:
    """Return a stable opaque identifier for a new domain record."""

    return uuid4().hex


def utc_now() -> str:
    """Return an ISO-8601 UTC timestamp suitable for SQLite text ordering."""

    return datetime.now(timezone.utc).isoformat()


class TaskMode(StrEnum):
    """Whether a task analyzes a solution or changes code."""

    PLAN = "plan"
    EXECUTE = "execute"


class CodingTaskStatus(StrEnum):
    """Persisted projection derived from all runs belonging to a task."""

    QUEUED = "queued"
    RUNNING = "running"
    WAITING_APPROVAL = "waiting_approval"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class RunStatus(StrEnum):
    """Lifecycle state of one Coding Agent execution attempt."""

    QUEUED = "queued"
    RUNNING = "running"
    WAITING_APPROVAL = "waiting_approval"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Provider(StrEnum):
    """Supported Coding Agent CLI providers."""

    CODEX = "codex"
    CLAUDE = "claude"


class PermissionLevel(StrEnum):
    """Unified execution permission profiles enforced by Shiori."""

    READ_ONLY = "read-only"
    WORKSPACE_WRITE = "workspace-write"
    FULL_ACCESS = "full-access"


class ApprovalType(StrEnum):
    """User decisions that may unblock a Coding Agent run."""

    REPOSITORY = "repository"
    PERMISSION = "permission"


class ApprovalStatus(StrEnum):
    """Lifecycle state of an explicit user approval request."""

    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"
    REVOKED = "revoked"
    EXPIRED = "expired"


class WorkspaceStatus(StrEnum):
    """Durable state of a managed Git worktree."""

    ACTIVE = "active"
    RETAINED = "retained"
    MISSING = "missing"


@dataclass(frozen=True)
class CodingTask:
    """A user development request owned by one Shiori manager role."""

    request_id: str
    delivery_key: str
    manager_role_id: str
    thread_id: str
    source_channel: str
    source_chat_id: str
    repository_id: str
    mode: TaskMode
    title: str
    request_text: str
    id: str = field(default_factory=new_id)
    plan_snapshot_id: str | None = None
    status: CodingTaskStatus = CodingTaskStatus.QUEUED
    room_id: str | None = None
    requester_id: str | None = None
    assignee_role_id: str | None = None
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)


@dataclass(frozen=True)
class CodingTaskRun:
    """One immutable-configuration execution attempt for a Coding Task."""

    task_id: str
    provider: Provider
    profile_id: str
    model: str
    effort: str
    permission_level: PermissionLevel
    timeout_seconds: int
    max_budget_usd: float | None = None
    id: str = field(default_factory=new_id)
    parent_run_id: str | None = None
    depends_on_run_ids: tuple[str, ...] = ()
    attempt: int = 1
    status: RunStatus = RunStatus.QUEUED
    workspace_id: str | None = None
    worktree_path: str | None = None
    baseline_commit: str | None = None
    branch_name: str | None = None
    cli_version: str | None = None
    cli_session_id: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    result_summary: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    created_at: str = field(default_factory=utc_now)


@dataclass(frozen=True)
class CodingTaskEvent:
    """Append-only audit event with a per-task monotonic sequence."""

    task_id: str
    sequence: int
    event_type: str
    request_id: str
    id: str = field(default_factory=new_id)
    run_id: str | None = None
    previous_status: str | None = None
    next_status: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=utc_now)


@dataclass(frozen=True)
class PlanSnapshot:
    """An immutable, user-confirmed implementation plan version."""

    task_id: str
    version: int
    content: str
    source_run_ids: tuple[str, ...]
    confirmed_by: str
    id: str = field(default_factory=new_id)
    confirmed_at: str = field(default_factory=utc_now)


@dataclass(frozen=True)
class ApprovalRequest:
    """A durable request for repository trust or elevated permission."""

    task_id: str
    approval_type: ApprovalType
    requested_scope: dict[str, Any]
    reason: str
    expires_at: str
    id: str = field(default_factory=new_id)
    run_id: str | None = None
    status: ApprovalStatus = ApprovalStatus.PENDING
    decided_at: str | None = None
    decision_source: str | None = None
    created_at: str = field(default_factory=utc_now)


@dataclass(frozen=True)
class CodingRepository:
    """A locally configured repository and its durable trust decision."""

    name: str
    root_path: str
    trusted: bool = False
    id: str = field(default_factory=new_id)
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)


@dataclass(frozen=True)
class CodingWorkspace:
    """A persisted worktree allocated to exactly one Coding Agent run."""

    run_id: str
    repository_id: str
    worktree_path: str
    baseline_commit: str
    branch_name: str
    id: str = field(default_factory=new_id)
    status: WorkspaceStatus = WorkspaceStatus.ACTIVE
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)
