"""Coding Agent domain models and persistence contracts."""

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
from .state_machine import (
    InvalidRunTransition,
    can_transition_run,
    derive_task_status,
    require_run_transition,
)
from .store import CodingAgentStore

__all__ = [
    "ApprovalRequest",
    "ApprovalStatus",
    "ApprovalType",
    "CodingAgentStore",
    "CodingRepository",
    "CodingTask",
    "CodingTaskEvent",
    "CodingTaskRun",
    "CodingTaskStatus",
    "CodingWorkspace",
    "InvalidRunTransition",
    "PermissionLevel",
    "PlanSnapshot",
    "Provider",
    "RunStatus",
    "TaskMode",
    "WorkspaceStatus",
    "can_transition_run",
    "derive_task_status",
    "require_run_transition",
]
