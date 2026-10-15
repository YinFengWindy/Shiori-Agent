"""Desktop-only global task RPC and generation-scoped invalidation events."""

import asyncio

from shiori_sdk.plugin_services import ServicePluginContext
from shiori_sdk.rpc import Concurrency

from .models import CodingTask
from .service import TaskService

_RUNNING = {"queued", "preparing", "running", "cancelling", "monitoring_stopped"}
_UNCANCELLABLE = {"completed", "cancelled", "cancelling", "monitoring_stopped"}


def task_title(task: CodingTask) -> str:
    """The first nonempty requirement line names a task without an invented title."""
    return next(
        (line.strip() for line in task.requirement.splitlines() if line.strip()), ""
    )


def task_summary(task: CodingTask) -> dict[str, object]:
    """One task list entry; small enough to reread on every invalidation."""
    latest = task.progress_events[-1] if task.progress_events else None
    return {
        "id": task.id,
        "title": task_title(task),
        "status": task.status,
        "stage": task.stage,
        "progress_detail": str(latest["detail"]) if latest else "",
        "progress_at": task.progress_updated_at,
        "role_id": task.target.role_id,
        "agent": task.agent,
        "repository": str(task.repository),
        "branch": task.branch,
        "created_at": task.created_at,
        "updated_at": task.updated_at,
        "revision": task.revision,
    }


def task_detail(task: CodingTask) -> dict[str, object]:
    """Everything the detail pane shows; action availability is decided here."""
    idle = task.worker is None or task.worker.done()
    return {
        **task_summary(task),
        "run_id": task.run_id,
        "requirement": task.requirement,
        "worktree": str(task.worktree or ""),
        "output": task.output[-16000:],
        "progress_events": [
            event for event in task.progress_events if event["run_id"] == task.run_id
        ],
        "progress_notice": task.progress_notice,
        "validation": list(task.validation),
        "summary": task.summary,
        "pr_url": task.pr_url,
        "error": task.error,
        "report_error": task.report_error,
        "can_continue": idle
        and task.worktree is not None
        and bool(task.pane_id)
        and task.status not in _RUNNING,
        "can_cancel": task.status not in _UNCANCELLABLE,
    }


class Dashboard:
    """Desktop sees all tasks; role tools keep their separate ownership checks."""

    def __init__(self, service: TaskService, ctx: ServicePluginContext):
        self.service, self.ctx = service, ctx
        self._pending: dict[str, int] = {}
        self._emitting: asyncio.Task[None] | None = None

    def register(self) -> None:
        """Register readers and controls only in the current plugin's RPC namespace."""
        self.ctx.rpc.register(
            "tasks.list", self.list_tasks, concurrency=Concurrency.READ_ONLY
        )
        self.ctx.rpc.register(
            "tasks.get", self.get_task, concurrency=Concurrency.READ_ONLY
        )
        self.ctx.rpc.register("tasks.continue", self.continue_task)
        self.ctx.rpc.register("tasks.cancel", self.cancel_task)
        self.ctx.effect("dashboard.subscription", self.service.subscribe(self.changed))

    def _require_active(self) -> None:
        if not self.ctx.process_resources.active:
            raise RuntimeError("Herdr 配置已替换，请刷新看板")

    def _task(self, payload: dict[str, object]) -> CodingTask:
        self._require_active()
        task = self.service.tasks.get(str(payload.get("task_id") or ""))
        if task is None:
            raise ValueError("任务不存在")
        return task

    def _detail(self, task: CodingTask) -> dict[str, object]:
        return {"instance_id": self.service.instance_id, "task": task_detail(task)}

    async def list_tasks(self, _payload: dict[str, object]) -> dict[str, object]:
        """Newest first; the process identity tells a fresh process from old revisions."""
        self._require_active()
        tasks = sorted(
            self.service.tasks.values(), key=lambda task: task.created_at, reverse=True
        )
        return {
            "instance_id": self.service.instance_id,
            "tasks": [task_summary(task) for task in tasks],
        }

    async def get_task(self, payload: dict[str, object]) -> dict[str, object]:
        """One task's current state, without slow Herdr terminal reads."""
        return self._detail(self._task(payload))

    async def continue_task(self, payload: dict[str, object]) -> dict[str, object]:
        """The desktop user's explicit action uses the same service as role tools."""
        task = self._task(payload)
        requirement = payload.get("requirement")
        if not isinstance(requirement, str):
            raise ValueError("追加要求不能为空")
        await self.service.continue_task(task.id, requirement, task.target.role_id)
        return self._detail(task)

    async def cancel_task(self, payload: dict[str, object]) -> dict[str, object]:
        """Cancellation remains pending until the shared service confirms it."""
        task = self._task(payload)
        await self.service.cancel_task(task.id, task.target.role_id)
        return self._detail(task)

    def changed(self, task: CodingTask) -> None:
        """Candidates and retired generations never take over the active event sink."""
        if not self.ctx.process_resources.active:
            return
        self._pending[task.id] = task.revision
        if self._emitting is None or self._emitting.done():
            self._emitting = self.ctx.background.spawn(
                self._emit(), name="dashboard-updates"
            )

    async def _emit(self) -> None:
        while self._pending and self.ctx.process_resources.active:
            pending, self._pending = self._pending, {}
            for task_id, revision in pending.items():
                _ = await self.ctx.rpc.emit(
                    "tasks.changed", {"task_id": task_id, "revision": revision}
                )
