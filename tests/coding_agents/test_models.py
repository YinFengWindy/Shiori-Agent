from dataclasses import FrozenInstanceError

import pytest

from coding_agents.models import (
    CodingTask,
    CodingTaskRun,
    PermissionLevel,
    Provider,
    RunStatus,
    TaskMode,
)


def test_domain_records_have_stable_defaults_and_are_frozen():
    task = CodingTask(
        request_id="request-1",
        delivery_key="delivery-1",
        manager_role_id="role-1",
        thread_id="thread-1",
        source_channel="desktop",
        source_chat_id="chat-1",
        repository_id="repo-1",
        mode=TaskMode.EXECUTE,
        title="Fix issue",
        request_text="Fix the issue",
    )
    run = CodingTaskRun(
        task_id=task.id,
        provider=Provider.CODEX,
        profile_id="codex-fast",
        model="test-model",
        effort="medium",
        permission_level=PermissionLevel.WORKSPACE_WRITE,
        timeout_seconds=60,
    )

    assert task.status.value == "queued"
    assert run.status is RunStatus.QUEUED
    assert run.depends_on_run_ids == ()
    assert task.created_at.endswith("+00:00")
    with pytest.raises(FrozenInstanceError):
        run.status = RunStatus.RUNNING  # type: ignore[misc]


def test_permission_values_match_cli_contract():
    assert [level.value for level in PermissionLevel] == [
        "read-only",
        "workspace-write",
        "full-access",
    ]
