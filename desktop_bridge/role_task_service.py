from __future__ import annotations

from collections.abc import Callable
from typing import Any


class RoleTaskService:
    """Builds and mutates the desktop read model for role-owned tasks."""

    def __init__(
        self,
        *,
        scheduler: Any | None,
        subagent_manager: Any | None,
        memory_optimizer: Any | None,
        session_key_for_role: Callable[[str], str],
    ) -> None:
        self._scheduler = scheduler
        self._subagent_manager = subagent_manager
        self._memory_optimizer = memory_optimizer
        self._session_key_for_role = session_key_for_role

    def list_tasks(self, role_id: str) -> list[dict[str, object]]:
        """Returns the current task snapshot owned by one role."""
        tasks = [
            *self._list_schedule_tasks(role_id),
            *self._list_subagent_tasks(role_id),
            *self._list_memory_tasks(role_id),
        ]
        return sorted(
            tasks,
            key=lambda task: (
                str(task.get("created_at") or task.get("next_run_at") or ""),
                str(task.get("id") or ""),
            ),
        )

    async def cancel_task(self, role_id: str, task_id: str) -> list[dict[str, object]]:
        """Cancels a cancellable task after validating its role ownership."""
        if self._scheduler is not None:
            scheduled_job = next(
                (
                    job
                    for job in self._scheduler.list_jobs()
                    if job.id == task_id and job.role_id == role_id
                ),
                None,
            )
            if scheduled_job is not None:
                if not self._scheduler.cancel_job(task_id):
                    raise RuntimeError("取消任务失败")
                return self.list_tasks(role_id)

        manager = self._subagent_manager
        if manager is not None:
            role_session_key = self._session_key_for_role(role_id)
            subagent_job = next(
                (
                    job
                    for job in manager.list_running_jobs()
                    if str(job.get("job_id") or "") == task_id
                    and str(job.get("origin_chat_id") or "") == role_session_key
                ),
                None,
            )
            if subagent_job is not None:
                if not await manager.cancel(task_id):
                    raise RuntimeError("取消任务失败")
                return self.list_tasks(role_id)

        raise KeyError("角色任务不存在")

    def _list_schedule_tasks(self, role_id: str) -> list[dict[str, object]]:
        scheduler = self._scheduler
        if scheduler is None:
            return []
        return [
            {
                "id": job.id,
                "role_id": job.role_id,
                "kind": "schedule",
                "status": "running" if scheduler.is_job_active(job.id) else "scheduled",
                "label": job.name or job.id[:8],
                "detail": job.message or job.prompt or "",
                "created_at": job.created_at.isoformat(),
                "next_run_at": job.fire_at.isoformat(),
                "cancellable": True,
            }
            for job in scheduler.list_jobs()
            if job.role_id == role_id
        ]

    def _list_subagent_tasks(self, role_id: str) -> list[dict[str, object]]:
        manager = self._subagent_manager
        if manager is None:
            return []
        role_session_key = self._session_key_for_role(role_id)
        return [
            {
                "id": str(job["job_id"]),
                "role_id": role_id,
                "kind": "subagent",
                "status": str(job.get("status") or "running"),
                "label": str(job["label"]),
                "detail": str(job["task"]),
                "created_at": str(job["started_at"]),
                "next_run_at": "",
                "cancellable": True,
            }
            for job in manager.list_running_jobs()
            if str(job.get("origin_chat_id") or "") == role_session_key
        ]

    def _list_memory_tasks(self, role_id: str) -> list[dict[str, object]]:
        optimizer = self._memory_optimizer
        if optimizer is None or optimizer.active_role_id != role_id:
            return []
        return [
            {
                "id": f"memory-optimizer:{role_id}",
                "role_id": role_id,
                "kind": "memory_maintenance",
                "status": "running",
                "label": "记忆维护",
                "detail": "整理角色记忆与自我认知",
                "created_at": optimizer.active_started_at,
                "next_run_at": "",
                "cancellable": False,
            }
        ]
