"""Queued-run scheduling and adapter execution for the orchestrator."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from .adapters import AdapterError, AdapterEvent, TaskRunSpec
from .execution import AdapterExecutor
from .models import (
    ApprovalStatus,
    ApprovalType,
    CodingRepository,
    CodingTask,
    CodingTaskRun,
    CodingWorkspace,
    PermissionLevel,
    RunStatus,
    new_id,
)
from .orchestrator_support import project_parallel_limit, safe_environment
from .permissions import PermissionApproval, PermissionPolicy
from .profiles import ProfileRegistry
from .repository_trust import TrustedRepository
from .store import CodingAgentStore
from .workspace import WorktreeManager, WorkspaceError, WorkspaceRequest


class OrchestratorExecutionMixin:
    """Own the process-facing half of Coding Agent orchestration."""

    config: Any
    store: CodingAgentStore
    executor: AdapterExecutor
    profile_registry: ProfileRegistry
    permission_policy: PermissionPolicy
    worktree_manager: WorktreeManager
    _repositories: dict[str, TrustedRepository]
    _base_refs: dict[str, str]
    _approvals: dict[str, PermissionApproval]
    _tasks: dict[str, asyncio.Task[None]]
    _closing: bool
    _global_limit: asyncio.Semaphore
    _repo_limits: dict[str, asyncio.Semaphore]
    _profile_limits: dict[str, asyncio.Semaphore]

    async def _publish_completion(
        self, task: CodingTask, run: CodingTaskRun, summary: str
    ) -> None:
        raise NotImplementedError

    def _schedule(self, run_id: str, *, resume: bool = False) -> None:
        if self._closing or run_id in self._tasks:
            return
        self._tasks[run_id] = asyncio.create_task(
            self._execute_run(run_id, resume=resume)
        )

    async def _execute_run(self, run_id: str, *, resume: bool = False) -> None:
        run = self.store.get_run(run_id)
        if run is None:
            return
        task = self.store.get_task(run.task_id)
        if task is None:
            return
        wake_queued = True
        try:
            dependencies = [
                self.store.get_run(dep_id) for dep_id in run.depends_on_run_ids
            ]
            if any(dep is None for dep in dependencies):
                failed = self._fail_run(
                    task, run, "dependency_failed", "依赖 Run 不存在"
                )
                if failed is not None:
                    await self._publish_completion(
                        task, failed, failed.error_message or ""
                    )
                return
            if any(
                dep.status in {RunStatus.FAILED, RunStatus.CANCELLED}
                for dep in dependencies
                if dep
            ):
                failed = self._fail_run(
                    task, run, "dependency_failed", "前置 Run 未成功"
                )
                if failed is not None:
                    await self._publish_completion(
                        task, failed, failed.error_message or ""
                    )
                return
            if any(
                dep.status is not RunStatus.SUCCEEDED for dep in dependencies if dep
            ):
                wake_queued = False
                return
            profile = self.profile_registry.get(run.profile_id)
            repository = self._repositories.get(task.repository_id)
            if repository is None:
                failed = self._fail_run(
                    task,
                    run,
                    "repository_not_trusted",
                    "仓库信任状态不可恢复",
                )
                if failed is not None:
                    await self._publish_completion(
                        task, failed, failed.error_message or ""
                    )
                return
            permission = self.permission_policy.resolve(
                run_id=run.id,
                provider=run.provider,
                mode=task.mode,
                requested_level=run.permission_level,
                approval=self._permission_approval_for_run(run.id),
                outer_sandbox_available=True,
            )
            profile_limit = self._profile_limits.setdefault(
                profile.profile_id,
                asyncio.Semaphore(profile.max_parallel_runs or 1),
            )
            repository_limit = self._repo_limits.setdefault(
                task.repository_id,
                asyncio.Semaphore(
                    project_parallel_limit(self.config, task.repository_id)
                ),
            )
            async with self._global_limit, repository_limit, profile_limit:
                current = self.store.get_run(run.id)
                expected_status = RunStatus.RUNNING if resume else RunStatus.QUEUED
                if current is None or current.status is not expected_status:
                    return
                worktree_path = self._prepare_worktree(
                    task,
                    run,
                    current,
                    repository,
                    resume=resume,
                )
                if not resume:
                    self.store.transition_run(
                        run.id,
                        RunStatus.RUNNING,
                        event_type="run_started",
                        request_id=task.request_id,
                    )
                spec = self._run_spec(
                    task,
                    run,
                    worktree_path,
                    permission.outer_sandbox_profile,
                )
                if resume:
                    from .adapters import ResumeSpec

                    result = await self.executor.resume(
                        run.provider,
                        ResumeSpec(spec, current.cli_session_id or ""),
                        on_event=lambda event: self._record_event(task, run, event),
                    )
                else:
                    result = await self.executor.execute(
                        run.provider,
                        spec,
                        on_event=lambda event: self._record_event(task, run, event),
                    )
                terminal_status = (
                    RunStatus.SUCCEEDED
                    if result.success
                    else RunStatus.CANCELLED
                    if result.error_code == "cancelled"
                    else RunStatus.FAILED
                )
                finished = self.store.transition_run(
                    run.id,
                    terminal_status,
                    event_type=f"run_{terminal_status.value}",
                    request_id=task.request_id,
                    cli_session_id=result.session_id,
                    result_summary=result.summary,
                    error_code=result.error_code,
                    error_message=result.error_message,
                )
                await self._publish_completion(task, finished, result.summary)
        except asyncio.CancelledError:
            current = self.store.get_run(run.id)
            if current is not None and current.status is RunStatus.RUNNING:
                self.store.transition_run(
                    run.id,
                    RunStatus.CANCELLED,
                    event_type="run_cancelled",
                    request_id=task.request_id,
                    error_code="cancelled",
                    error_message="运行时已关闭",
                )
            raise
        except (AdapterError, WorkspaceError, OSError, ValueError) as exc:
            failed = self._fail_run(
                task,
                run,
                getattr(exc, "code", "process_crashed"),
                str(exc),
            )
            if failed is not None:
                await self._publish_completion(
                    task, failed, failed.error_message or ""
                )
        finally:
            self._tasks.pop(run_id, None)
            if wake_queued:
                self._wake_queued()

    def _prepare_worktree(
        self,
        task: CodingTask,
        run: CodingTaskRun,
        current: CodingTaskRun,
        repository: TrustedRepository,
        *,
        resume: bool,
    ) -> Path:
        if resume:
            return Path(current.worktree_path or "")
        if current.worktree_path:
            workspace = self.store.get_workspace_by_run(run.id)
            if workspace is None or workspace.worktree_path != current.worktree_path:
                raise WorkspaceError(
                    "path_boundary_violation",
                    "Run worktree 与持久化 workspace 映射不一致",
                )
            path = self.worktree_manager.validate_cleanup_target(
                task.repository_id,
                run.id,
                current.worktree_path,
            )
            if not path.is_dir():
                raise WorkspaceError(
                    "worktree_create_failed", "持久化 worktree 已丢失"
                )
            return path
        request = WorkspaceRequest(
            workspace_id=new_id(),
            run_id=run.id,
            repository_id=task.repository_id,
            repository_path=repository.root_path,
            base_ref=self._base_refs.get(task.repository_id, "HEAD"),
        )
        try:
            snapshot = self.worktree_manager.create(request)
        except WorkspaceError as exc:
            if exc.code != "worktree_create_failed":
                raise
            snapshot = self.worktree_manager.adopt_existing(request)
        if self.store.get_repository(task.repository_id) is None:
            self.store.create_repository(
                CodingRepository(
                    id=task.repository_id,
                    name=repository.name,
                    root_path=str(repository.root_path),
                    trusted=False,
                )
            )
        self.store.create_workspace(
            CodingWorkspace(
                id=snapshot.workspace_id,
                run_id=run.id,
                repository_id=task.repository_id,
                worktree_path=str(snapshot.worktree_path),
                baseline_commit=snapshot.baseline_commit,
                branch_name=snapshot.branch_name,
            )
        )
        return snapshot.worktree_path

    async def _record_event(
        self, task: CodingTask, run: CodingTaskRun, event: AdapterEvent
    ) -> None:
        session_id = str(
            event.payload.get("session_id") or event.payload.get("thread_id") or ""
        ).strip()
        if session_id:
            self.store.update_run_session(run.id, session_id)
        self.store.append_event(
            task_id=task.id,
            run_id=run.id,
            event_type=event.event_type,
            request_id=task.request_id,
            payload=dict(event.payload),
        )

    def _permission_approval_for_run(
        self, run_id: str
    ) -> PermissionApproval | None:
        for approval in self._approvals.values():
            if approval.run_id == run_id:
                return approval
        for approval in self.store.list_approvals(status=ApprovalStatus.APPROVED):
            if (
                approval.run_id == run_id
                and approval.approval_type is ApprovalType.PERMISSION
                and approval.requested_scope.get("permission_level")
                == PermissionLevel.FULL_ACCESS.value
            ):
                return PermissionApproval(
                    approval_id=approval.id,
                    run_id=run_id,
                    approved_level=PermissionLevel.FULL_ACCESS,
                )
        return None

    def _run_spec(
        self,
        task: CodingTask,
        run: CodingTaskRun,
        worktree: Path,
        sandbox_profile: str | None,
    ) -> TaskRunSpec:
        return TaskRunSpec(
            run_id=run.id,
            task=self._run_task_text(task, run),
            worktree=worktree,
            model=run.model,
            effort=run.effort,
            permission_level=run.permission_level,
            timeout_seconds=run.timeout_seconds,
            environment=safe_environment(),
            sandbox_profile=sandbox_profile,
            max_budget_usd=run.max_budget_usd,
            output_file=worktree / f".shiori-coding-agent-{run.id}.txt",
        )

    def _run_task_text(self, task: CodingTask, run: CodingTaskRun) -> str:
        for event in reversed(self.store.list_events(task.id)):
            if event.run_id == run.id and event.event_type == "run_queued":
                text = str(event.payload.get("task") or "").strip()
                if text:
                    return text
        if task.plan_snapshot_id:
            snapshot = self.store.get_plan_snapshot(task.plan_snapshot_id)
            if snapshot is not None:
                return f"{task.request_text}\n\n已确认方案：\n{snapshot.content}"
        return task.request_text

    def _fail_run(
        self,
        task: CodingTask,
        run: CodingTaskRun,
        code: str,
        message: str,
    ) -> CodingTaskRun | None:
        current = self.store.get_run(run.id)
        if current is None or current.status in {
            RunStatus.SUCCEEDED,
            RunStatus.FAILED,
            RunStatus.CANCELLED,
        }:
            return current
        return self.store.transition_run(
            run.id,
            RunStatus.FAILED,
            event_type="run_failed",
            request_id=task.request_id,
            error_code=code,
            error_message=message,
        )

    def _fail_recovered_run(
        self, run: CodingTaskRun, code: str, message: str
    ) -> CodingTaskRun | None:
        task = self.store.get_task(run.task_id)
        if task is not None:
            return self._fail_run(task, run, code, message)
        return None

    def _completion_was_published(self, run: CodingTaskRun) -> bool:
        return any(
            event.run_id == run.id
            and event.event_type == "completion_published"
            and event.payload.get("status") == run.status.value
            for event in self.store.list_events(run.task_id)
        )

    def _wake_queued(self) -> None:
        if self._closing:
            return
        for run in self.store.list_recoverable_runs():
            if run.status is RunStatus.QUEUED:
                self._schedule(run.id)
