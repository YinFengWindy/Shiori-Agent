"""Task visibility and cancellation across current and draining runtime versions."""

from core.roles.errors import RoleNotFoundError
from core.common.runtime_scope import bind_runtime
from desktop_bridge.role_task_service import RoleTaskService


class RuntimeRoleTasks:
    """Keeps accepted background jobs addressable after their originating UI retires."""

    def __init__(self, app, roles) -> None:
        self._app = app
        self._roles = roles

    def _sources(self):
        for generation in self._app.retained_generations:
            core = generation.core
            spawn = core.tools.get_tool("spawn")
            yield generation, RoleTaskService(
                scheduler=core.scheduler,
                subagent_manager=spawn.manager if spawn is not None else None,
                memory_optimizer=core.memory_optimizer,
                session_key_for_role=lambda role_id: f"role:{role_id}",
            )

    def list_tasks(self, role_id: str):
        """Merges background work while deduplicating the shared scheduler."""
        if self._roles.get_role(role_id) is None:
            raise RoleNotFoundError(role_id)
        tasks = {
            str(task["id"]): task
            for _, source in self._sources()
            for task in source.list_tasks(role_id)
        }
        return sorted(
            tasks.values(),
            key=lambda task: (str(task.get("created_at") or ""), str(task["id"])),
        )

    async def cancel_task(self, role_id: str, task_id: str):
        """Cancels through the original task owner and preserves its completion version."""
        if not task_id:
            raise ValueError("task_id 不能为空")
        self.list_tasks(role_id)
        for generation, source in self._sources():
            if any(task["id"] == task_id for task in source.list_tasks(role_id)):
                async with generation.acquire() as lease:
                    with bind_runtime(lease):
                        await source.cancel_task(role_id, task_id)
                return self.list_tasks(role_id)
        raise KeyError("角色任务不存在")
