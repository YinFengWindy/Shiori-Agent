import sqlite3
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import pytest

from coding_agents.models import (
    ApprovalRequest,
    ApprovalStatus,
    ApprovalType,
    CodingRepository,
    CodingTask,
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
from coding_agents.state_machine import InvalidRunTransition
from coding_agents.store import CodingAgentStore, SCHEMA_VERSION


def make_task(*, delivery_key="delivery-1", role_id="role-1", thread_id="thread-1"):
    return CodingTask(
        request_id=f"request-{delivery_key}",
        delivery_key=delivery_key,
        manager_role_id=role_id,
        thread_id=thread_id,
        source_channel="desktop",
        source_chat_id="chat-1",
        repository_id="repo-1",
        mode=TaskMode.EXECUTE,
        title="Fix issue",
        request_text="Fix the issue",
    )


def make_run(task, *, provider=Provider.CODEX, attempt=1, parent_run_id=None):
    return CodingTaskRun(
        task_id=task.id,
        parent_run_id=parent_run_id,
        attempt=attempt,
        provider=provider,
        profile_id=f"{provider}-fast",
        model="test-model",
        effort="medium",
        permission_level=PermissionLevel.WORKSPACE_WRITE,
        timeout_seconds=60,
        max_budget_usd=3.5,
    )


def create_task(store, **task_kwargs):
    task = make_task(**task_kwargs)
    run = make_run(task)
    assert store.create_task_with_run(task, run)[2]
    return task, run


def test_schema_initialization_is_versioned_and_complete(tmp_path):
    db_path = tmp_path / "coding-agents.db"
    with CodingAgentStore(db_path) as store:
        assert store.schema_version == SCHEMA_VERSION

    with sqlite3.connect(db_path) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
    assert {
        "coding_tasks",
        "coding_task_runs",
        "coding_task_events",
        "coding_plan_snapshots",
        "coding_approval_requests",
        "coding_repositories",
        "coding_workspaces",
        "coding_artifacts",
    } <= tables


def test_newer_schema_version_is_rejected_without_mutation(tmp_path):
    db_path = tmp_path / "newer.db"
    with sqlite3.connect(db_path) as connection:
        connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 1}")

    with pytest.raises(RuntimeError, match="newer than supported"):
        CodingAgentStore(db_path)

    with sqlite3.connect(db_path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION + 1


def test_create_roundtrip_and_delivery_key_are_idempotent(tmp_path):
    with CodingAgentStore(tmp_path / "store.db") as store:
        task, run = create_task(store)
        duplicate_task = make_task(delivery_key=task.delivery_key)
        duplicate_run = make_run(duplicate_task)

        persisted_task, persisted_run, created = store.create_task_with_run(
            duplicate_task, duplicate_run
        )

        assert not created
        assert persisted_task == task
        assert persisted_run == run
        assert persisted_run.max_budget_usd == 3.5
        assert store.get_task_by_delivery_key(task.delivery_key) == task
        assert store.list_runs(task_id=task.id) == [run]
        events = store.list_events(task.id)
        assert [(event.sequence, event.event_type) for event in events] == [
            (1, "run_queued")
        ]


def test_parallel_and_retry_runs_do_not_conflict(tmp_path):
    with CodingAgentStore(tmp_path / "store.db") as store:
        task, first_run = create_task(store)
        parallel = make_run(task)
        retry = make_run(task, attempt=2, parent_run_id=first_run.id)

        store.create_run(parallel, request_id="parallel")
        store.create_run(retry, request_id="retry")

        assert {run.id for run in store.list_runs(task_id=task.id)} == {
            first_run.id,
            parallel.id,
            retry.id,
        }
        assert [event.sequence for event in store.list_events(task.id)] == [1, 2, 3]


def test_transition_updates_run_task_and_event_in_one_commit(tmp_path):
    with CodingAgentStore(tmp_path / "store.db") as store:
        task, run = create_task(store)

        running = store.transition_run(
            run.id,
            RunStatus.RUNNING,
            event_type="process_started",
            request_id="start-1",
            cli_session_id="session-1",
        )
        succeeded = store.transition_run(
            run.id,
            RunStatus.SUCCEEDED,
            event_type="result_collected",
            request_id="finish-1",
            result_summary="done",
        )

        assert running.started_at is not None
        assert succeeded.finished_at is not None
        assert succeeded.result_summary == "done"
        assert store.get_task(task.id).status is CodingTaskStatus.SUCCEEDED
        events = store.list_events(task.id)
        assert [event.sequence for event in events] == [1, 2, 3]
        assert events[-1].previous_status == "running"
        assert events[-1].next_status == "succeeded"


def test_transition_rolls_back_when_event_insert_fails(tmp_path):
    db_path = tmp_path / "store.db"
    with CodingAgentStore(db_path) as store:
        task, run = create_task(store)
        with sqlite3.connect(db_path) as connection:
            connection.execute(
                """CREATE TRIGGER reject_exploding_event
                   BEFORE INSERT ON coding_task_events
                   WHEN NEW.event_type = 'explode'
                   BEGIN SELECT RAISE(ABORT, 'event rejected'); END"""
            )

        with pytest.raises(sqlite3.IntegrityError):
            store.transition_run(
                run.id,
                RunStatus.RUNNING,
                event_type="explode",
                request_id="start-1",
            )

        assert store.get_run(run.id).status is RunStatus.QUEUED
        assert store.get_task(task.id).status is CodingTaskStatus.QUEUED
        assert len(store.list_events(task.id)) == 1


def test_transition_rejects_invalid_state_and_unknown_result_fields(tmp_path):
    with CodingAgentStore(tmp_path / "store.db") as store:
        _task, run = create_task(store)
        with pytest.raises(InvalidRunTransition):
            store.transition_run(
                run.id,
                RunStatus.SUCCEEDED,
                event_type="done",
                request_id="request-1",
            )
        with pytest.raises(ValueError, match="unsupported run result fields"):
            store.transition_run(
                run.id,
                RunStatus.RUNNING,
                event_type="start",
                request_id="request-1",
                arbitrary_column="bad",
            )


def test_workspace_update_and_owner_filters(tmp_path):
    with CodingAgentStore(tmp_path / "store.db") as store:
        first_task, first_run = create_task(store)
        create_task(store, delivery_key="delivery-2", role_id="role-2", thread_id="thread-2")

        updated = store.update_run_workspace(
            first_run.id,
            workspace_id="workspace-1",
            worktree_path="D:/worktrees/run-1",
            baseline_commit="abc123",
            branch_name="shiori/run-1",
        )

        assert updated.workspace_id == "workspace-1"
        assert store.list_tasks(manager_role_id="role-1") == [first_task]
        assert store.list_runs(thread_id="thread-1") == [updated]


def test_repository_crud_persists_trust_across_store_reopen(tmp_path):
    db_path = tmp_path / "store.db"
    repository = CodingRepository(
        id="repo-1",
        name="example",
        root_path=str(tmp_path / "repository"),
    )
    with CodingAgentStore(db_path) as store:
        store.create_coding_repository(repository)
        trusted = store.set_repository_trusted(repository.id, trusted=True)

        assert trusted.trusted is True
        assert store.get_repository_by_root_path(repository.root_path) == trusted
        assert store.list_coding_repositories(trusted=True) == [trusted]

    with CodingAgentStore(db_path) as store:
        assert store.get_coding_repository(repository.id).trusted is True


def test_workspace_mapping_roundtrip_updates_run_and_enforces_uniqueness(tmp_path):
    with CodingAgentStore(tmp_path / "store.db") as store:
        repository = CodingRepository(
            id="repo-1",
            name="example",
            root_path=str(tmp_path / "repository"),
            trusted=True,
        )
        store.create_repository(repository)
        _task, run = create_task(store)
        workspace = CodingWorkspace(
            id="workspace-1",
            run_id=run.id,
            repository_id=repository.id,
            worktree_path=str(tmp_path / "worktrees" / run.id),
            baseline_commit="abc123",
            branch_name=f"shiori/{run.id}",
        )

        store.create_coding_workspace(workspace)

        assert store.get_workspace_by_run(run.id) == workspace
        assert store.get_coding_run(run.id).workspace_id == workspace.id
        assert store.get_coding_run(run.id).baseline_commit == "abc123"
        retained = store.update_coding_workspace_status(
            workspace.id, WorkspaceStatus.RETAINED
        )
        assert retained.status is WorkspaceStatus.RETAINED
        assert store.list_coding_workspaces(status="retained") == [retained]

        duplicate = replace(workspace, id="workspace-2")
        with pytest.raises(sqlite3.IntegrityError):
            store.create_workspace(duplicate)


def test_recovery_queries_include_nonterminal_runs_and_pending_approvals(tmp_path):
    with CodingAgentStore(tmp_path / "store.db") as store:
        task, run = create_task(store)
        store.transition_run(
            run.id,
            RunStatus.WAITING_APPROVAL,
            event_type="approval_needed",
            request_id="request-1",
        )
        approval = ApprovalRequest(
            task_id=task.id,
            run_id=run.id,
            approval_type=ApprovalType.PERMISSION,
            requested_scope={"permission": "full-access"},
            reason="Network access required",
            expires_at="2099-01-01T00:00:00+00:00",
        )
        store.create_approval(approval, request_id="request-1")

        assert store.list_recoverable_runs() == [store.get_run(run.id)]
        assert store.get_pending_approval(approval.id) == approval
        assert store.list_pending_approvals() == [approval]

        decided = store.decide_approval(
            approval.id,
            ApprovalStatus.APPROVED,
            decision_source="desktop:user-message-2",
            request_id="request-2",
        )
        assert decided.status is ApprovalStatus.APPROVED
        assert store.get_pending_approval(approval.id) is None


def test_approval_decision_and_run_transition_are_atomic(tmp_path):
    with CodingAgentStore(tmp_path / "store.db") as store:
        task, run = create_task(store)
        store.transition_run(
            run.id,
            RunStatus.WAITING_APPROVAL,
            event_type="approval_needed",
            request_id="request-1",
        )
        approval = ApprovalRequest(
            task_id=task.id,
            run_id=run.id,
            approval_type=ApprovalType.PERMISSION,
            requested_scope={"permission_level": "full-access"},
            reason="Elevated permission",
            expires_at="2099-01-01T00:00:00+00:00",
        )
        store.create_approval(approval, request_id="request-1")

        decided, queued, _ = store.resolve_approval(
            approval.id,
            ApprovalStatus.APPROVED,
            decision_source="desktop:user",
            request_id="request-2",
            run_next_status=RunStatus.QUEUED,
            run_event_type="permission_approved",
        )

        assert decided.status is ApprovalStatus.APPROVED
        assert queued is not None
        assert queued.status is RunStatus.QUEUED
        assert store.get_task(task.id).status is CodingTaskStatus.QUEUED


def test_cancelling_waiting_run_revokes_pending_approval_atomically(tmp_path):
    with CodingAgentStore(tmp_path / "store.db") as store:
        task, run = create_task(store)
        store.transition_run(
            run.id,
            RunStatus.WAITING_APPROVAL,
            event_type="approval_needed",
            request_id="request-1",
        )
        approval = ApprovalRequest(
            task_id=task.id,
            run_id=run.id,
            approval_type=ApprovalType.REPOSITORY,
            requested_scope={"repository_id": "repo-1"},
            reason="Repository trust",
            expires_at="2099-01-01T00:00:00+00:00",
        )
        store.create_approval(approval, request_id="request-1")

        cancelled = store.cancel_run_with_approvals(
            run.id,
            request_id="request-2",
            decision_source="desktop:user",
        )

        assert cancelled.status is RunStatus.CANCELLED
        assert store.get_approval(approval.id).status is ApprovalStatus.REVOKED


def test_plan_snapshots_are_versioned_and_immutable(tmp_path):
    with CodingAgentStore(tmp_path / "store.db") as store:
        task, run = create_task(store)
        snapshot = PlanSnapshot(
            task_id=task.id,
            version=1,
            content="Implement with a shared service.",
            source_run_ids=(run.id,),
            confirmed_by="user-1",
        )

        assert store.create_plan_snapshot(snapshot, request_id="confirm-1") == snapshot
        assert store.get_plan_snapshot(snapshot.id) == snapshot
        assert store.get_task(task.id).plan_snapshot_id == snapshot.id
        with pytest.raises(sqlite3.IntegrityError):
            store.create_plan_snapshot(
                replace(snapshot, id="another-id", content="Overwrite"),
                request_id="confirm-2",
            )


def test_event_sequences_are_monotonic_across_store_connections(tmp_path):
    db_path = tmp_path / "store.db"
    first = CodingAgentStore(db_path)
    second = CodingAgentStore(db_path)
    task, _run = create_task(first)

    try:
        stores = [first, second] * 5
        with ThreadPoolExecutor(max_workers=5) as executor:
            list(
                executor.map(
                    lambda pair: pair[1].append_event(
                        task_id=task.id,
                        event_type="assistant_delta",
                        request_id=f"delta-{pair[0]}",
                    ),
                    enumerate(stores),
                )
            )

        assert [event.sequence for event in first.list_events(task.id)] == list(range(1, 12))
    finally:
        first.close()
        second.close()
