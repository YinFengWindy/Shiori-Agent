from dataclasses import replace

import pytest

from coding_agents.models import (
    CodingTask,
    CodingTaskRun,
    PermissionLevel,
    Provider,
    TaskMode,
)
from coding_agents.orchestrator_context import (
    CodingStartContext,
    validate_explicit_approval,
    validate_idempotent_replay,
)


def _context(*, message: str = "同意 approval-1"):
    return CodingStartContext(
        manager_role_id="role-1",
        thread_id="thread-1",
        source_channel="desktop",
        source_chat_id="chat-1",
        request_id="request-2",
        delivery_key="delivery-1",
        role_config_version="role-version-1",
        role_source="passive_turn",
        role_work_kind="passive_turn",
        role_context_created_at="2026-07-16T00:00:00+08:00",
        current_user_message=message,
        current_user_source_ref="desktop:chat-1:message-2",
    )


def _task_and_run():
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
        profile_id="default",
        model="test-model",
        effort="medium",
        permission_level=PermissionLevel.WORKSPACE_WRITE,
        timeout_seconds=60,
    )
    return task, run


def test_explicit_approval_requires_current_user_message_to_name_request():
    with pytest.raises(PermissionError, match="approval_id"):
        validate_explicit_approval(
            _context(message="同意"),
            approval_id="approval-1",
            accepted=True,
            scope="once",
        )


def test_explicit_approval_requires_current_user_message_to_state_decision():
    with pytest.raises(PermissionError, match="明确表达"):
        validate_explicit_approval(
            _context(message="请查看 approval-1"),
            approval_id="approval-1",
            accepted=True,
            scope="once",
        )


def test_delivery_key_replay_rejects_different_role_owner():
    task, run = _task_and_run()
    other_role = replace(_context(), manager_role_id="role-2")

    with pytest.raises(PermissionError, match="其他角色会话"):
        validate_idempotent_replay(
            task,
            run,
            other_role,
            repository_id=task.repository_id,
            mode=task.mode,
            request_text=task.request_text,
            profile_id=run.profile_id,
            permission_level=run.permission_level,
        )
