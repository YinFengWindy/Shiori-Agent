from __future__ import annotations

from collections.abc import Callable
from typing import Any

from desktop_bridge.schedule_role_task_service import ScheduleRoleTaskService


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
        self._schedule_tasks = ScheduleRoleTaskService(
            scheduler=scheduler,
            session_key_for_role=session_key_for_role,
        )
        self._subagent_manager = subagent_manager
        self._memory_optimizer = memory_optimizer
        self._session_key_for_role = session_key_for_role

    def list_tasks(self, role_id: str) -> list[dict[str, object]]:
        """Returns the current task snapshot owned by one role."""
        tasks = [
            *self._schedule_tasks.list_tasks(role_id),
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
        if self._schedule_tasks.cancel_task(role_id, task_id):
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

    def create_schedule_task(self, role_id: str, **fields: str) -> dict[str, object]:
        """Creates a scheduled task bound to one role's desktop session."""
        return self._schedule_tasks.create_task(role_id, **fields)

    def update_schedule_task(
        self,
        role_id: str,
        task_id: str,
        **fields: str,
    ) -> dict[str, object]:
        """Updates an idle role-owned scheduled task."""
        return self._schedule_tasks.update_task(role_id, task_id, **fields)

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
                "editable": False,
                "schedule": None,
            }
            for job in manager.list_running_jobs()
            if str(job.get("origin_chat_id") or "") == role_session_key
        ]

    def _list_memory_tasks(self, role_id: str) -> list[dict[str, object]]:
        optimizer = self._memory_optimizer
        if optimizer is None or optimizer.active_role_id != role_id:
            return []
        return [{
            "id": f"memory-optimizer:{role_id}",
            "role_id": role_id,
            "kind": "memory_maintenance",
            "status": "running",
            "label": "记忆维护",
            "detail": "整理角色记忆与自我认知",
            "created_at": optimizer.active_started_at,
            "next_run_at": "",
            "cancellable": False,
            "editable": False,
            "schedule": None,
        }]
