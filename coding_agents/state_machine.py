"""Pure lifecycle rules for Coding Agent tasks and runs."""

from __future__ import annotations

from collections.abc import Iterable

from .models import CodingTaskStatus, RunStatus


TERMINAL_RUN_STATUSES = frozenset(
    {RunStatus.SUCCEEDED, RunStatus.FAILED, RunStatus.CANCELLED}
)

_RUN_TRANSITIONS: dict[RunStatus, frozenset[RunStatus]] = {
    RunStatus.QUEUED: frozenset(
        {
            RunStatus.RUNNING,
            RunStatus.WAITING_APPROVAL,
            RunStatus.FAILED,
            RunStatus.CANCELLED,
        }
    ),
    RunStatus.WAITING_APPROVAL: frozenset(
        {RunStatus.QUEUED, RunStatus.FAILED, RunStatus.CANCELLED}
    ),
    RunStatus.RUNNING: frozenset(
        {
            RunStatus.WAITING_APPROVAL,
            RunStatus.SUCCEEDED,
            RunStatus.FAILED,
            RunStatus.CANCELLED,
        }
    ),
    RunStatus.SUCCEEDED: frozenset(),
    RunStatus.FAILED: frozenset(),
    RunStatus.CANCELLED: frozenset(),
}


class InvalidRunTransition(ValueError):
    """Raised when a caller attempts a forbidden run lifecycle change."""

    def __init__(self, previous: RunStatus, next_status: RunStatus):
        super().__init__(f"invalid run status transition: {previous} -> {next_status}")
        self.previous = previous
        self.next_status = next_status


def can_transition_run(previous: RunStatus, next_status: RunStatus) -> bool:
    """Return whether `previous` may transition to `next_status`."""

    return next_status in _RUN_TRANSITIONS[previous]


def require_run_transition(previous: RunStatus, next_status: RunStatus) -> None:
    """Validate a run transition and raise a stable domain error if invalid."""

    if not can_transition_run(previous, next_status):
        raise InvalidRunTransition(previous, next_status)


def derive_task_status(statuses: Iterable[RunStatus]) -> CodingTaskStatus:
    """Derive the task projection from all of its current run states."""

    values = tuple(statuses)
    if not values:
        return CodingTaskStatus.QUEUED
    if RunStatus.RUNNING in values:
        return CodingTaskStatus.RUNNING
    if RunStatus.WAITING_APPROVAL in values:
        return CodingTaskStatus.WAITING_APPROVAL
    if RunStatus.QUEUED in values:
        return CodingTaskStatus.QUEUED
    if RunStatus.FAILED in values:
        return CodingTaskStatus.FAILED
    if RunStatus.CANCELLED in values:
        return CodingTaskStatus.CANCELLED
    return CodingTaskStatus.SUCCEEDED
