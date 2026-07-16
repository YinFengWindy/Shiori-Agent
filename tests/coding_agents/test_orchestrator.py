from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from bus.events import CodingAgentCompletionItem
from bus.queue import MessageBus
from coding_agents.adapters import AdapterResult, ProbeResult
from coding_agents.models import (
    ApprovalStatus,
    CodingTaskStatus,
    PermissionLevel,
    RunStatus,
    TaskMode,
)
from coding_agents.orchestrator import CodingAgentOrchestrator, CodingStartContext
from coding_agents.repository_trust import RepositoryResolution, TrustedRepository
from coding_agents.workspace import WorkspaceSnapshot


_COMMIT = "a" * 40


class _Trust:
    def __init__(self, repository: TrustedRepository, *, requires_approval: bool = False):
        self.repository = repository
        self.requires_approval = requires_approval

    def resolve(self, _candidate):
        return RepositoryResolution(self.repository, self.requires_approval)

    def register(self, _repository):
        return None

    def approve(self, resolution, _approval):
        return RepositoryResolution(resolution.repository, False)


class _Workspace:
    def __init__(self, root: Path):
        self.root = root

    def create(self, request):
        path = self.root / request.run_id
        path.mkdir(parents=True, exist_ok=True)
        return WorkspaceSnapshot(
            workspace_id=request.workspace_id,
            run_id=request.run_id,
            repository_id=request.repository_id,
            repository_path=request.repository_path,
            worktree_path=path,
            baseline_commit=_COMMIT,
            branch_name=f"shiori/run-{request.run_id}",
            source_was_dirty=False,
        )


class _Registry:
    async def probe_all(self):
        return {}


class _Executor:
    def __init__(self):
        self.registry = _Registry()
        self.calls: list[str] = []
        self.tasks: list[str] = []

    async def probe(self, _provider):
        return ProbeResult(True, version="test-cli", sandbox_available=True)

    async def execute(self, _provider, spec, *, on_event=None):
        self.calls.append(spec.run_id)
        self.tasks.append(spec.task)
        if on_event is not None:
            await on_event(SimpleNamespace(event_type="test_summary", payload={"ok": True}))
        await asyncio.sleep(0)
        return AdapterResult(True, 0, f"done:{spec.run_id}", f"session:{spec.run_id}")

    async def cancel(self, _run_id):
        return True


def _config(tmp_path: Path, *, enabled: bool = True):
    profile = SimpleNamespace(
        provider="codex",
        model="test-model",
        effort="medium",
        timeout_seconds=30,
        max_parallel_runs=2,
        max_permission_level="full-access",
        max_budget_usd=None,
    )
    coding = SimpleNamespace(
        enabled=enabled,
        worktree_root=str(tmp_path / "worktrees"),
        default_profile="default",
        max_parallel_runs=2,
        profiles={"default": profile},
        projects={},
    )
    return SimpleNamespace(coding_agents=coding)


def _context(request_id: str = "request-1", message: str = "明确请求"):
    return CodingStartContext(
        manager_role_id="role-1",
        thread_id="thread-1",
        source_channel="desktop",
        source_chat_id="chat-1",
        request_id=request_id,
        delivery_key=request_id,
        role_config_version="role-version-1",
        role_source="passive_turn",
        role_work_kind="passive_turn",
        role_context_created_at="2026-07-16T00:00:00+08:00",
        current_user_message=message,
        current_user_source_ref="telegram:chat-1:1",
    )


@pytest.mark.asyncio
async def test_start_run_executes_and_publishes_typed_completion(tmp_path: Path) -> None:
    from coding_agents.store import CodingAgentStore

    repository = TrustedRepository("repo-1", "demo", tmp_path, _COMMIT)
    bus = MessageBus()
    executor = _Executor()
    orchestrator = CodingAgentOrchestrator(
        config=_config(tmp_path),
        workspace=tmp_path,
        bus=bus,
        store=CodingAgentStore(":memory:"),
        trust_service=_Trust(repository),
        worktree_manager=_Workspace(tmp_path / "worktrees"),
        executor=executor,
    )
    result = await orchestrator.start_run(
        context=_context(),
        repository=str(tmp_path),
        task="修复测试",
        mode=TaskMode.EXECUTE,
        permission_level=PermissionLevel.WORKSPACE_WRITE,
    )
    await asyncio.sleep(0.05)
    assert executor.calls == [result.run.id]
    item = await asyncio.wait_for(bus.consume_inbound(), timeout=1)
    assert isinstance(item, CodingAgentCompletionItem)
    assert item.event.status == RunStatus.SUCCEEDED.value
    assert item.metadata["role_config_version"] == "role-version-1"
    assert item.metadata["transport_channel"] == "desktop"
    assert item.metadata["role_work_kind"] == "passive_turn"
    await orchestrator.close()


@pytest.mark.asyncio
async def test_add_run_uses_same_task_and_waits_for_dependency(tmp_path: Path) -> None:
    from coding_agents.store import CodingAgentStore

    repository = TrustedRepository("repo-1", "demo", tmp_path, _COMMIT)
    executor = _Executor()
    orchestrator = CodingAgentOrchestrator(
        config=_config(tmp_path),
        workspace=tmp_path,
        bus=MessageBus(),
        store=CodingAgentStore(":memory:"),
        trust_service=_Trust(repository),
        worktree_manager=_Workspace(tmp_path / "worktrees"),
        executor=executor,
    )
    first = await orchestrator.start_run(
        context=_context(),
        repository=str(tmp_path),
        task="实现登录修复",
        mode=TaskMode.EXECUTE,
    )
    second = await orchestrator.add_run(
        context=_context("request-2"),
        task_id=first.task.id,
        task_text="审查登录修复",
        depends_on_run_ids=(first.run.id,),
    )

    await asyncio.sleep(0.1)

    assert executor.calls == [first.run.id, second.run.id]
    assert executor.tasks == ["实现登录修复", "审查登录修复"]
    await orchestrator.close()


@pytest.mark.asyncio
async def test_first_repository_use_waits_for_later_approval(tmp_path: Path) -> None:
    from coding_agents.store import CodingAgentStore

    repository = TrustedRepository("repo-1", "demo", tmp_path, _COMMIT)
    bus = MessageBus()
    executor = _Executor()
    orchestrator = CodingAgentOrchestrator(
        config=_config(tmp_path),
        workspace=tmp_path,
        bus=bus,
        store=CodingAgentStore(":memory:"),
        trust_service=_Trust(repository, requires_approval=True),
        worktree_manager=_Workspace(tmp_path / "worktrees"),
        executor=executor,
    )
    result = await orchestrator.start_run(
        context=_context("request-create"),
        repository=str(tmp_path),
        task="先讨论",
        mode=TaskMode.PLAN,
        permission_level=PermissionLevel.FULL_ACCESS,
    )
    assert result.run.status is RunStatus.WAITING_APPROVAL
    with pytest.raises(PermissionError):
        await orchestrator.approve(
            context=_context("request-create", f"同意 {result.approval_id}"),
            approval_id=result.approval_id or "",
            decision="approve",
        )
    approved = await orchestrator.approve(
        context=_context("request-approve", f"同意 {result.approval_id}"),
        approval_id=result.approval_id or "",
        decision="approve",
    )
    assert approved.run.status is RunStatus.QUEUED
    await orchestrator.close()


@pytest.mark.asyncio
async def test_repository_then_full_access_requires_two_user_approvals(
    tmp_path: Path,
) -> None:
    from coding_agents.store import CodingAgentStore

    repository = TrustedRepository("repo-1", "demo", tmp_path, _COMMIT)
    store = CodingAgentStore(":memory:")
    orchestrator = CodingAgentOrchestrator(
        config=_config(tmp_path),
        workspace=tmp_path,
        bus=MessageBus(),
        store=store,
        trust_service=_Trust(repository, requires_approval=True),
        worktree_manager=_Workspace(tmp_path / "worktrees"),
        executor=_Executor(),
    )
    started = await orchestrator.start_run(
        context=_context("request-create"),
        repository=str(tmp_path),
        task="执行高权限任务",
        mode=TaskMode.EXECUTE,
        permission_level=PermissionLevel.FULL_ACCESS,
    )
    repository_approved = await orchestrator.approve(
        context=_context(
            "request-repository", f"同意 {started.approval_id}"
        ),
        approval_id=started.approval_id or "",
        decision="approve",
    )

    assert repository_approved.run.status is RunStatus.WAITING_APPROVAL
    assert repository_approved.approval_id != started.approval_id

    permission_approved = await orchestrator.approve(
        context=_context(
            "request-permission", f"同意 {repository_approved.approval_id}"
        ),
        approval_id=repository_approved.approval_id or "",
        decision="approve",
    )
    assert permission_approved.run.status is RunStatus.QUEUED
    await orchestrator.close()


@pytest.mark.asyncio
async def test_cancel_waiting_run_revokes_pending_approval(tmp_path: Path) -> None:
    from coding_agents.store import CodingAgentStore

    repository = TrustedRepository("repo-1", "demo", tmp_path, _COMMIT)
    store = CodingAgentStore(":memory:")
    orchestrator = CodingAgentOrchestrator(
        config=_config(tmp_path),
        workspace=tmp_path,
        bus=MessageBus(),
        store=store,
        trust_service=_Trust(repository, requires_approval=True),
        worktree_manager=_Workspace(tmp_path / "worktrees"),
        executor=_Executor(),
    )
    started = await orchestrator.start_run(
        context=_context(),
        repository=str(tmp_path),
        task="等待授权",
        mode=TaskMode.EXECUTE,
    )

    cancelled = await orchestrator.cancel(
        run_id=started.run.id,
        context=_context("request-cancel"),
    )

    assert cancelled.status is RunStatus.CANCELLED
    approval = store.get_approval(started.approval_id or "")
    assert approval is not None
    assert approval.status is ApprovalStatus.REVOKED
    await orchestrator.close()


@pytest.mark.asyncio
async def test_expired_approval_atomically_fails_waiting_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from coding_agents.store import CodingAgentStore

    class _ExpiredDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2100, 1, 1, tzinfo=tz)

    repository = TrustedRepository("repo-1", "demo", tmp_path, _COMMIT)
    store = CodingAgentStore(":memory:")
    orchestrator = CodingAgentOrchestrator(
        config=_config(tmp_path),
        workspace=tmp_path,
        bus=MessageBus(),
        store=store,
        trust_service=_Trust(repository, requires_approval=True),
        worktree_manager=_Workspace(tmp_path / "worktrees"),
        executor=_Executor(),
    )
    started = await orchestrator.start_run(
        context=_context("request-create"),
        repository=str(tmp_path),
        task="等待仓库授权",
        mode=TaskMode.EXECUTE,
    )
    monkeypatch.setattr("coding_agents.orchestrator.datetime", _ExpiredDatetime)

    with pytest.raises(ValueError, match="已过期"):
        await orchestrator.approve(
            context=_context("request-expired", f"同意 {started.approval_id}"),
            approval_id=started.approval_id or "",
            decision="approve",
        )

    approval = store.get_approval(started.approval_id or "")
    run = store.get_run(started.run.id)
    task = store.get_task(started.task.id)
    assert approval is not None
    assert approval.status is ApprovalStatus.EXPIRED
    assert run is not None
    assert run.status is RunStatus.FAILED
    assert run.error_code == "approval_expired"
    assert task is not None
    assert task.status is CodingTaskStatus.FAILED
    expiry_events = [
        event
        for event in store.list_events(task.id)
        if event.event_type == "approval_expired"
    ]
    assert [event.next_status for event in expiry_events] == [
        ApprovalStatus.EXPIRED.value,
        RunStatus.FAILED.value,
    ]
    await orchestrator.close()
