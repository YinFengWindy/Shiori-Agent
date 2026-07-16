"""Deterministic orchestration service for role-owned Coding Agent runs."""
from __future__ import annotations

import asyncio
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from bus.events import CodingAgentCompletionItem
from bus.internal_events import CodingAgentCompletionEvent
from bus.queue import MessageBus
from .adapters import AdapterError, AdapterEvent
from .execution import AdapterExecutor, AdapterRegistry
from .models import (
    ApprovalRequest,
    ApprovalStatus,
    ApprovalType,
    CodingTask,
    CodingTaskRun,
    CodingRepository,
    CodingWorkspace,
    PermissionLevel,
    PlanSnapshot,
    Provider,
    RunStatus,
    TaskMode,
    new_id,
)
from .permissions import PermissionApproval, PermissionPolicy
from .profiles import ProfileRegistry
from .orchestrator_context import (
    CodingStartContext,
    CodingStartResult,
    validate_explicit_approval,
    validate_idempotent_replay,
    validate_plan_confirmation,
)
from .orchestrator_support import profile_mapping, run_json, task_json
from .orchestrator_repositories import load_repository_state
from .orchestrator_execution import OrchestratorExecutionMixin
from .repository_trust import (
    RepositoryApproval,
    RepositoryResolution,
    RepositoryTrustScope,
    RepositoryTrustService,
    paths_equal,
)
from .store import CodingAgentStore
from .workspace import WorktreeManager, WorkspaceError, WorkspaceRequest


class CodingAgentOrchestrator(OrchestratorExecutionMixin):
    """Owns Coding Agent persistence and provider execution lifecycles."""

    def __init__(
        self,
        *,
        config: Any,
        workspace: Path,
        bus: MessageBus,
        store: CodingAgentStore | None = None,
        trust_service: RepositoryTrustService | None = None,
        worktree_manager: WorktreeManager | None = None,
        profile_registry: ProfileRegistry | None = None,
        permission_policy: PermissionPolicy | None = None,
        executor: AdapterExecutor | None = None,
    ) -> None:
        self.config = config
        self.workspace = Path(workspace)
        self.bus = bus
        coding_config = config.coding_agents
        self.store = store or CodingAgentStore(self.workspace / "coding_agents.db")
        self.trust_service = trust_service or RepositoryTrustService()
        self.worktree_manager = worktree_manager or WorktreeManager(
            coding_config.worktree_root
        )
        self.profile_registry = profile_registry or ProfileRegistry.from_mapping(
            profile_mapping(coding_config.profiles),
            default_profile_id=coding_config.default_profile or None,
        )
        self.permission_policy = permission_policy or PermissionPolicy()
        self.executor = executor or AdapterExecutor(AdapterRegistry.with_defaults())
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._started = False
        self._closing = False
        self._global_limit = asyncio.Semaphore(coding_config.max_parallel_runs)
        self._repo_limits: dict[str, asyncio.Semaphore] = {}
        self._profile_limits: dict[str, asyncio.Semaphore] = {}
        self._repositories, self._base_refs = load_repository_state(
            config,
            self.store,
            self.trust_service,
        )
        self._approvals: dict[str, PermissionApproval] = {}

    async def start(self) -> None:
        """Recover persisted queued and running work without auto-approving it."""

        if self._started:
            return
        self._closing = False
        self._started = True
        for run in self.store.list_runs():
            if run.status in {
                RunStatus.SUCCEEDED,
                RunStatus.FAILED,
                RunStatus.CANCELLED,
            } and not self._completion_was_published(run):
                task = self.store.get_task(run.task_id)
                if task is not None:
                    await self._publish_completion(
                        task,
                        run,
                        run.result_summary or run.error_message or "",
                    )
        for run in self.store.list_recoverable_runs():
            if run.status is RunStatus.RUNNING:
                failed = self._fail_recovered_run(
                    run,
                    "session_unrecoverable",
                    "无法确认崩溃前受管进程已退出，拒绝盲目恢复",
                )
                if failed is not None:
                    task = self.store.get_task(run.task_id)
                    if task is not None:
                        await self._publish_completion(
                            task, failed, failed.error_message or ""
                        )
                continue
            if run.status is RunStatus.WAITING_APPROVAL:
                if not self._completion_was_published(run):
                    task = self.store.get_task(run.task_id)
                    if task is not None:
                        await self._publish_completion(task, run, "等待用户审批")
                continue
            self._schedule(run.id)

    async def close(self) -> None:
        """Cancel active tasks and close the independent persistence store."""

        self._closing = True
        tasks = list(self._tasks.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._tasks.clear()
        self.store.close()
        self._started = False

    async def profiles(self, *, probe: bool = False) -> list[dict[str, Any]]:
        """List named profiles, optionally including live CLI availability."""

        probes: dict[Provider, Any] = {}
        if probe:
            probes = await self.executor.registry.probe_all()
        result: list[dict[str, Any]] = []
        for profile in self.profile_registry.list():
            item: dict[str, Any] = {
                "profile_id": profile.profile_id,
                "provider": profile.provider.value,
                "model": profile.model,
                "effort": profile.effort.value,
                "timeout_seconds": profile.timeout_seconds,
                "max_permission_level": profile.max_permission_level.value,
                "max_budget_usd": float(profile.max_budget_usd)
                if profile.max_budget_usd is not None
                else None,
            }
            if probe:
                status = probes.get(profile.provider)
                item["available"] = bool(status and status.available)
                item["cli_version"] = status.version if status else None
                item["error_code"] = status.error_code if status else "provider_unavailable"
            result.append(item)
        return result

    async def start_run(
        self,
        *,
        context: CodingStartContext,
        repository: str,
        task: str,
        mode: TaskMode | str,
        profile_id: str | None = None,
        permission_level: PermissionLevel | str = PermissionLevel.WORKSPACE_WRITE,
        label: str = "",
        depends_on_run_ids: tuple[str, ...] = (),
        plan_snapshot_id: str | None = None,
    ) -> CodingStartResult:
        """Accept a task, creating an approval gate when required."""

        if not self.config.coding_agents.enabled:
            raise RuntimeError("Coding Agent 功能未启用")
        if not context.manager_role_id or not context.thread_id:
            raise ValueError("Coding Agent 缺少角色或会话上下文")
        normalized_mode = TaskMode(mode)
        if depends_on_run_ids:
            raise ValueError("首个 Run 不能依赖其他 Task；请先创建 Task 再添加 Run")
        if plan_snapshot_id:
            plan_snapshot = self.store.get_plan_snapshot(plan_snapshot_id)
            plan_task = (
                self.store.get_task(plan_snapshot.task_id)
                if plan_snapshot is not None
                else None
            )
            if plan_task is None or (
                plan_task.manager_role_id,
                plan_task.thread_id,
            ) != (context.manager_role_id, context.thread_id):
                raise PermissionError("PlanSnapshot 不属于当前角色会话")
        profile = self.profile_registry.select(explicit_profile_id=profile_id)
        probe = await self.executor.probe(profile.provider)
        if not probe.available or not probe.version:
            raise AdapterError(
                probe.error_code or "provider_unavailable",
                probe.error or f"Provider 不可用: {profile.provider.value}",
            )
        requested_permission = PermissionLevel.READ_ONLY if TaskMode(mode) is TaskMode.PLAN else PermissionLevel(permission_level)
        if (profile.provider is Provider.CLAUDE or requested_permission is PermissionLevel.FULL_ACCESS) and not probe.sandbox_available:
            raise AdapterError("sandbox_unavailable", "当前 Provider 缺少所需外层 sandbox runner")
        resolution = self._resolve_repository(repository)
        task_record = CodingTask(
            request_id=context.request_id,
            delivery_key=context.delivery_key,
            manager_role_id=context.manager_role_id,
            thread_id=context.thread_id,
            source_channel=context.source_channel,
            source_chat_id=context.source_chat_id,
            repository_id=resolution.repository.repository_id,
            mode=normalized_mode,
            title=(label.strip() or task.strip()[:80] or "Coding Task"),
            request_text=task.strip(),
            plan_snapshot_id=plan_snapshot_id,
        )
        snapshot = self.profile_registry.snapshot(
            profile.profile_id,
            permission_level=(
                requested_permission
            ),
            cli_version=probe.version,
        )
        run_record = CodingTaskRun(
            task_id=task_record.id,
            provider=snapshot.provider,
            profile_id=snapshot.profile_id,
            model=snapshot.model,
            effort=snapshot.effort.value,
            permission_level=snapshot.permission_level,
            timeout_seconds=snapshot.timeout_seconds,
            max_budget_usd=float(snapshot.max_budget_usd)
            if snapshot.max_budget_usd is not None
            else None,
            depends_on_run_ids=tuple(depends_on_run_ids),
            cli_version=snapshot.cli_version,
        )
        task_record, run_record, created = self.store.create_task_with_run(
            task_record,
            run_record,
            event_payload={
                "repository": str(resolution.repository.root_path),
                "role_context": context.role_metadata(),
            },
        )
        if not created:
            validate_idempotent_replay(
                task_record,
                run_record,
                context,
                repository_id=resolution.repository.repository_id,
                mode=normalized_mode,
                request_text=task.strip(),
                profile_id=snapshot.profile_id,
                permission_level=snapshot.permission_level,
            )
            return CodingStartResult(task_record, run_record, reused=True)
        approval_id: str | None = None
        if resolution.requires_approval:
            approval_id = self._create_approval(
                task_record,
                run_record,
                ApprovalType.REPOSITORY,
                {
                    "repository_id": resolution.repository.repository_id,
                    "repository_path": str(resolution.repository.root_path),
                    "scope_options": ["once", "persistent"],
                },
                "首次使用该本地仓库需要明确授权",
            )
            run_record = self.store.transition_run(
                run_record.id,
                RunStatus.WAITING_APPROVAL,
                event_type="waiting_repository_approval",
                request_id=context.request_id,
                payload={"approval_id": approval_id},
            )
            await self._publish_completion(task_record, run_record, "等待仓库授权")
            return CodingStartResult(task_record, run_record, approval_id=approval_id)
        self._repositories[resolution.repository.repository_id] = resolution.repository
        if run_record.permission_level is PermissionLevel.FULL_ACCESS:
            approval_id = self._create_approval(
                task_record,
                run_record,
                ApprovalType.PERMISSION,
                {"permission_level": PermissionLevel.FULL_ACCESS.value},
                "full-access 需要用户明确批准",
            )
            run_record = self.store.transition_run(
                run_record.id,
                RunStatus.WAITING_APPROVAL,
                event_type="waiting_permission_approval",
                request_id=context.request_id,
                payload={"approval_id": approval_id},
            )
            await self._publish_completion(task_record, run_record, "等待权限授权")
            return CodingStartResult(task_record, run_record, approval_id=approval_id)
        self._schedule(run_record.id)
        return CodingStartResult(task_record, run_record)

    async def add_run(
        self,
        *,
        context: CodingStartContext,
        task_id: str,
        task_text: str,
        profile_id: str | None = None,
        permission_level: PermissionLevel | str = PermissionLevel.WORKSPACE_WRITE,
        depends_on_run_ids: tuple[str, ...] = (),
        label: str = "",
    ) -> CodingStartResult:
        """Add a parallel Run to an existing role-owned Task."""

        task = self.store.get_task(task_id)
        if task is None or (task.manager_role_id, task.thread_id) != (
            context.manager_role_id,
            context.thread_id,
        ):
            raise PermissionError("Task 不属于当前角色会话")
        profile = self.profile_registry.select(explicit_profile_id=profile_id)
        probe = await self.executor.probe(profile.provider)
        if not probe.available or not probe.version:
            raise AdapterError(
                probe.error_code or "provider_unavailable",
                probe.error or f"Provider 不可用: {profile.provider.value}",
            )
        snapshot = self.profile_registry.snapshot(
            profile.profile_id,
            permission_level=permission_level,
            cli_version=probe.version,
        )
        run = CodingTaskRun(
            task_id=task.id,
            provider=snapshot.provider,
            profile_id=snapshot.profile_id,
            model=snapshot.model,
            effort=snapshot.effort.value,
            permission_level=snapshot.permission_level,
            timeout_seconds=snapshot.timeout_seconds,
            max_budget_usd=float(snapshot.max_budget_usd)
            if snapshot.max_budget_usd is not None
            else None,
            depends_on_run_ids=tuple(depends_on_run_ids),
            cli_version=snapshot.cli_version,
        )
        run = self.store.create_run(
            run,
            request_id=context.request_id,
            event_payload={"label": label.strip(), "task": task_text.strip()},
        )
        if run.permission_level is PermissionLevel.FULL_ACCESS:
            approval_id = self._create_approval(
                task,
                run,
                ApprovalType.PERMISSION,
                {"permission_level": PermissionLevel.FULL_ACCESS.value},
                "full-access 需要用户明确批准",
            )
            run = self.store.transition_run(
                run.id,
                RunStatus.WAITING_APPROVAL,
                event_type="waiting_permission_approval",
                request_id=context.request_id,
                payload={"approval_id": approval_id},
            )
            await self._publish_completion(task, run, "等待权限授权")
            return CodingStartResult(task, run, approval_id=approval_id)
        self._schedule(run.id)
        return CodingStartResult(task, run)

    async def approve(
        self,
        *,
        context: CodingStartContext,
        approval_id: str,
        decision: str,
        scope: str = "once",
    ) -> CodingStartResult:
        """Apply an explicit later-turn approval bound to the owning role/session."""

        approval = self.store.get_approval(approval_id)
        if approval is None or approval.status is not ApprovalStatus.PENDING:
            raise ValueError("approval 不存在、已处理或已过期")
        task = self.store.get_task(approval.task_id)
        run = self.store.get_run(approval.run_id or "") if approval.run_id else None
        if task is None or run is None:
            raise ValueError("approval 关联的 Task/Run 不存在")
        if (task.manager_role_id, task.thread_id, task.source_channel, task.source_chat_id) != (
            context.manager_role_id,
            context.thread_id,
            context.source_channel,
            context.source_chat_id,
        ):
            raise PermissionError("approval 不属于当前角色会话")
        if self._approval_request_id(approval_id) == context.request_id:
            raise PermissionError("审批必须来自创建申请之后的新用户消息")
        if datetime.fromisoformat(approval.expires_at) <= datetime.now(timezone.utc):
            _, run, _ = self.store.resolve_approval(
                approval_id,
                ApprovalStatus.EXPIRED,
                decision_source="boundary",
                request_id=context.request_id,
                run_next_status=RunStatus.FAILED,
                run_event_type="approval_expired",
                error_code="approval_expired",
                error_message="审批已过期",
            )
            assert run is not None
            await self._publish_completion(task, run, "审批已过期")
            raise ValueError("approval 已过期")
        normalized = decision.strip().lower()
        if normalized not in {"approve", "approved", "allow", "yes", "deny", "denied", "no"}:
            raise ValueError("decision 必须明确为 approve 或 deny")
        accepted = normalized in {"approve", "approved", "allow", "yes"}
        validate_explicit_approval(
            context,
            approval_id=approval_id,
            accepted=accepted,
            scope=scope,
        )
        decision_source = f"{context.source_channel}:{context.source_chat_id}"
        if not accepted:
            _, run, _ = self.store.resolve_approval(
                approval_id,
                ApprovalStatus.DENIED,
                decision_source=decision_source,
                request_id=context.request_id,
                run_next_status=RunStatus.CANCELLED,
                run_event_type="approval_denied",
                error_code="permission_denied",
                error_message="用户拒绝了审批",
            )
            assert run is not None
            await self._publish_completion(task, run, "审批被拒绝")
            return CodingStartResult(task, run, approval_id=approval_id)
        if approval.approval_type is ApprovalType.REPOSITORY:
            repository_path = str(approval.requested_scope.get("repository_path") or "")
            resolution = self.trust_service.resolve(repository_path)
            requested_repository_id = str(
                approval.requested_scope.get("repository_id") or ""
            )
            if (
                resolution.repository.repository_id != requested_repository_id
                or not paths_equal(
                    resolution.repository.root_path,
                    Path(repository_path).resolve(strict=True),
                )
            ):
                raise PermissionError("仓库内容在审批期间已变化，请重新申请")
            selected_scope = RepositoryTrustScope.PERSISTENT if scope == "persistent" else RepositoryTrustScope.ONCE
            approved = self.trust_service.approve(
                resolution,
                RepositoryApproval(
                    approval_id=approval_id,
                    repository_id=resolution.repository.repository_id,
                    scope=selected_scope,
                ),
            )
            self._repositories[approved.repository.repository_id] = approved.repository
            existing_repository = self.store.get_repository(approved.repository.repository_id)
            if existing_repository is None:
                self.store.create_repository(
                    CodingRepository(
                        id=approved.repository.repository_id,
                        name=approved.repository.name,
                        root_path=str(approved.repository.root_path),
                        trusted=selected_scope is RepositoryTrustScope.PERSISTENT,
                    )
                )
            elif selected_scope is RepositoryTrustScope.PERSISTENT:
                self.store.update_repository_trust(
                    approved.repository.repository_id,
                    trusted=True,
                )
            if run.permission_level is PermissionLevel.FULL_ACCESS:
                followup = ApprovalRequest(
                    task_id=task.id,
                    run_id=run.id,
                    approval_type=ApprovalType.PERMISSION,
                    requested_scope={
                        "permission_level": PermissionLevel.FULL_ACCESS.value
                    },
                    reason="full-access 需要用户明确批准",
                    expires_at=(
                        datetime.now(timezone.utc) + timedelta(hours=24)
                    ).isoformat(),
                )
                self.store.resolve_approval(
                    approval_id,
                    ApprovalStatus.APPROVED,
                    decision_source=decision_source,
                    request_id=context.request_id,
                    followup=followup,
                )
                await self._publish_completion(task, run, "等待权限授权")
                return CodingStartResult(task, run, approval_id=followup.id)
            _, run, _ = self.store.resolve_approval(
                approval_id,
                ApprovalStatus.APPROVED,
                decision_source=decision_source,
                request_id=context.request_id,
                run_next_status=RunStatus.QUEUED,
                run_event_type="repository_approved",
            )
        else:
            self._approvals[approval_id] = PermissionApproval(
                approval_id=approval_id,
                run_id=run.id,
                approved_level=PermissionLevel.FULL_ACCESS,
            )
            _, run, _ = self.store.resolve_approval(
                approval_id,
                ApprovalStatus.APPROVED,
                decision_source=decision_source,
                request_id=context.request_id,
                run_next_status=RunStatus.QUEUED,
                run_event_type="permission_approved",
            )
        assert run is not None
        self._schedule(run.id)
        return CodingStartResult(task, run, approval_id=approval_id)

    def list(self, *, manager_role_id: str, thread_id: str) -> list[dict[str, Any]]:
        """List only tasks owned by the current role and conversation."""

        tasks = self.store.list_tasks(manager_role_id=manager_role_id, thread_id=thread_id)
        result: list[dict[str, Any]] = []
        for task in tasks:
            runs = self.store.list_runs(task_id=task.id)
            result.append({"task": task_json(task), "runs": [run_json(run) for run in runs]})
        return result

    async def cancel(self, *, run_id: str, context: CodingStartContext) -> CodingTaskRun:
        """Cancel a queued or active run while preserving its worktree."""

        run = self.store.get_run(run_id)
        if run is None:
            raise ValueError("Run 不存在")
        task = self.store.get_task(run.task_id)
        if task is None or (task.manager_role_id, task.thread_id) != (context.manager_role_id, context.thread_id):
            raise PermissionError("Run 不属于当前角色会话")
        if run.status in {RunStatus.QUEUED, RunStatus.WAITING_APPROVAL}:
            run = self.store.cancel_run_with_approvals(
                run.id,
                request_id=context.request_id,
                decision_source=f"{context.source_channel}:{context.source_chat_id}",
            )
            await self._publish_completion(task, run, "已取消")
            return run
        if run.status is RunStatus.RUNNING:
            execution = self._tasks.get(run.id)
            for _ in range(3):
                if await self.executor.cancel(run.id):
                    break
                if execution is None or execution.done():
                    break
                await asyncio.sleep(0)
            if execution is not None:
                await asyncio.shield(execution)
            return self.store.get_run(run.id) or run
        return run

    async def confirm_plan(
        self,
        *,
        task_id: str,
        content: str,
        source_run_ids: tuple[str, ...],
        confirmed_by: str,
        context: CodingStartContext,
    ) -> dict[str, Any]:
        """Persist an immutable plan snapshot after a user confirmation."""

        task = self.store.get_task(task_id)
        if task is None or (task.manager_role_id, task.thread_id) != (context.manager_role_id, context.thread_id):
            raise PermissionError("Task 不属于当前角色会话")
        validate_plan_confirmation(context, task)
        version = len(self.store.list_plan_snapshots(task_id)) + 1
        snapshot = self.store.create_plan_snapshot(
            PlanSnapshot(
                task_id=task_id,
                version=version,
                content=content,
                source_run_ids=source_run_ids,
                confirmed_by=confirmed_by,
            ),
            request_id=context.request_id,
        )
        return {"plan_snapshot_id": snapshot.id, "version": snapshot.version}

    async def _publish_completion(self, task: CodingTask, run: CodingTaskRun, summary: str) -> None:
        await self.bus.publish_inbound(
            CodingAgentCompletionItem(
                channel=task.source_channel,
                chat_id=task.source_chat_id,
                event=CodingAgentCompletionEvent(
                    task_id=task.id,
                    run_id=run.id,
                    label=task.title,
                    task=task.request_text,
                    mode=task.mode.value,
                    status=run.status.value,
                    provider=run.provider.value,
                    profile_id=run.profile_id,
                    result=summary or run.error_message or "",
                    thread_id=task.thread_id,
                    manager_role_id=task.manager_role_id,
                    request_id=task.request_id,
                    delivery_key=task.delivery_key,
                    error_code=run.error_code or "",
                    artifacts=(run.worktree_path,) if run.worktree_path else (),
                ),
                metadata=self._role_metadata(task),
            )
        )
        self.store.append_event(
            task_id=task.id,
            run_id=run.id,
            event_type="completion_published",
            request_id=task.request_id,
            payload={"status": run.status.value},
        )

    def _role_metadata(self, task: CodingTask) -> dict[str, Any]:
        for event in self.store.list_events(task.id):
            role_context = event.payload.get("role_context")
            if isinstance(role_context, dict):
                return {str(key): str(value) for key, value in role_context.items()}
        raise RuntimeError("Coding Task 缺少持久化 RoleExecutionContext")

    def _resolve_repository(self, candidate: str) -> RepositoryResolution:
        if candidate in self.config.coding_agents.projects:
            candidate = self.config.coding_agents.projects[candidate].repo_path
        return self.trust_service.resolve(candidate)

    def _create_approval(self, task: CodingTask, run: CodingTaskRun, approval_type: ApprovalType, scope: Mapping[str, Any], reason: str) -> str:
        approval = ApprovalRequest(
            task_id=task.id,
            run_id=run.id,
            approval_type=approval_type,
            requested_scope=dict(scope),
            reason=reason,
            expires_at=(datetime.now(timezone.utc) + timedelta(hours=24)).isoformat(),
        )
        self.store.create_approval(approval, request_id=task.request_id)
        return approval.id

    def _approval_request_id(self, approval_id: str) -> str:
        for event in self.store.list_events(self.store.get_approval(approval_id).task_id if self.store.get_approval(approval_id) else ""):
            if event.event_type == "approval_requested" and event.payload.get("approval_id") == approval_id:
                return event.request_id
        return ""
