import pytest

from coding_agents.models import CodingTaskStatus, RunStatus
from coding_agents.state_machine import (
    InvalidRunTransition,
    can_transition_run,
    derive_task_status,
    require_run_transition,
)


@pytest.mark.parametrize(
    ("previous", "next_status"),
    [
        (RunStatus.QUEUED, RunStatus.RUNNING),
        (RunStatus.QUEUED, RunStatus.WAITING_APPROVAL),
        (RunStatus.WAITING_APPROVAL, RunStatus.QUEUED),
        (RunStatus.RUNNING, RunStatus.WAITING_APPROVAL),
        (RunStatus.RUNNING, RunStatus.SUCCEEDED),
        (RunStatus.RUNNING, RunStatus.FAILED),
        (RunStatus.RUNNING, RunStatus.CANCELLED),
    ],
)
def test_all_core_run_transitions_are_accepted(previous, next_status):
    assert can_transition_run(previous, next_status)
    require_run_transition(previous, next_status)


@pytest.mark.parametrize("terminal", list({RunStatus.SUCCEEDED, RunStatus.FAILED, RunStatus.CANCELLED}))
def test_terminal_runs_cannot_be_reopened(terminal):
    with pytest.raises(InvalidRunTransition) as exc_info:
        require_run_transition(terminal, RunStatus.QUEUED)

    assert exc_info.value.previous is terminal


def test_same_status_is_not_a_transition():
    assert not can_transition_run(RunStatus.QUEUED, RunStatus.QUEUED)


@pytest.mark.parametrize(
    ("statuses", "expected"),
    [
        ([], CodingTaskStatus.QUEUED),
        ([RunStatus.QUEUED], CodingTaskStatus.QUEUED),
        ([RunStatus.QUEUED, RunStatus.RUNNING], CodingTaskStatus.RUNNING),
        ([RunStatus.QUEUED, RunStatus.WAITING_APPROVAL], CodingTaskStatus.WAITING_APPROVAL),
        ([RunStatus.SUCCEEDED, RunStatus.SUCCEEDED], CodingTaskStatus.SUCCEEDED),
        ([RunStatus.SUCCEEDED, RunStatus.FAILED], CodingTaskStatus.FAILED),
        ([RunStatus.SUCCEEDED, RunStatus.CANCELLED], CodingTaskStatus.CANCELLED),
    ],
)
def test_task_status_is_derived_from_all_runs(statuses, expected):
    assert derive_task_status(statuses) is expected
