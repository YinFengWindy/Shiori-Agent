"""Desktop-only global task RPC and generation-scoped invalidation events."""

import asyncio

from shiori_sdk.plugin_services import ServicePluginContext
from shiori_sdk.rpc import Concurrency

from .models import CodingTask
from .service import TaskService
from .task_management import cancel_task, continue_task, task_snapshot


class Dashboard:
    """Desktop sees all tasks; role tools keep their separate ownership checks."""

    def __init__(self, service: TaskService, ctx: ServicePluginContext):
        self.service, self.ctx = service, ctx
        self._pending: dict[str, int] = {}
        self._emitting: asyncio.Task[None] | None = None

    def register(self) -> None:
        """Register readers and controls only in the current plugin's RPC namespace."""
        self.ctx.rpc.register(
            "tasks.snapshot", self.snapshot, concurrency=Concurrency.READ_ONLY
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

    async def snapshot(self, _payload: dict[str, object]) -> dict[str, object]:
        """One authoritative snapshot, without slow Herdr terminal reads."""
        self._require_active()
        return {
            "instance_id": self.service.instance_id,
            "tasks": [task_snapshot(task) for task in self.service.tasks.values()],
        }

    async def continue_task(self, payload: dict[str, object]) -> dict[str, object]:
        """The desktop user's explicit action uses the same service as role tools."""
        task = self._task(payload)
        requirement = payload.get("requirement")
        if not isinstance(requirement, str):
            raise ValueError("追加要求不能为空")
        await continue_task(self.service, task.id, requirement, task.target.role_id)
        return {"task": task_snapshot(task)}

    async def cancel_task(self, payload: dict[str, object]) -> dict[str, object]:
        """Cancellation remains pending until the shared service confirms it."""
        task = self._task(payload)
        await cancel_task(self.service, task.id, task.target.role_id)
        return {"task": task_snapshot(task)}

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
