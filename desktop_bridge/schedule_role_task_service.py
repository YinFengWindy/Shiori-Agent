from __future__ import annotations

from collections.abc import Callable
from typing import Any

from agent.scheduler import DEFAULT_SCHEDULE_TIMEZONE
from desktop_bridge.schedule_role_task_presenter import serialize_schedule_role_task


class ScheduleRoleTaskService:
    """Owns desktop mutations and read models for role schedules."""

    def __init__(
        self,
        *,
        scheduler: Any | None,
        session_key_for_role: Callable[[str], str],
    ) -> None:
        self._scheduler = scheduler
        self._session_key_for_role = session_key_for_role

    def list_tasks(self, role_id: str) -> list[dict[str, object]]:
        """Returns scheduled tasks owned by one role."""
        if self._scheduler is None:
            return []
        return [
            self._serialize(job)
            for job in self._scheduler.list_jobs()
            if job.role_id == role_id
        ]

    def create_task(self, role_id: str, **fields: str) -> dict[str, object]:
        """Creates a schedule bound to one role's desktop session."""
        scheduler = self._require_scheduler()
        job = scheduler.create_job(
            **self._scheduler_fields(fields),
            channel="desktop",
            chat_id=self._session_key_for_role(role_id),
            role_id=role_id,
        )
        return self._serialize(job)

    def update_task(
        self,
        role_id: str,
        task_id: str,
        **fields: str,
    ) -> dict[str, object]:
        """Updates an idle schedule after scheduler ownership validation."""
        job = self._require_scheduler().update_job(
            task_id,
            role_id=role_id,
            **self._scheduler_fields(fields),
        )
        return self._serialize(job)

    def cancel_task(self, role_id: str, task_id: str) -> bool:
        """Cancels a matching role schedule and reports whether it existed."""
        if self._scheduler is None:
            return False
        matched = next(
            (
                job
                for job in self._scheduler.list_jobs()
                if job.id == task_id and job.role_id == role_id
            ),
            None,
        )
        if matched is None:
            return False
        if not self._scheduler.cancel_job(task_id):
            raise RuntimeError("取消任务失败")
        return True

    def _serialize(self, job: Any) -> dict[str, object]:
        scheduler = self._require_scheduler()
        return serialize_schedule_role_task(
            job,
            running=scheduler.is_job_active(job.id),
        )

    def _require_scheduler(self) -> Any:
        if self._scheduler is None:
            raise RuntimeError("计划任务服务不可用")
        return self._scheduler

    @staticmethod
    def _scheduler_fields(fields: dict[str, str]) -> dict[str, str]:
        return {
            "name": fields.get("name", ""),
            "tier": fields.get("tier", ""),
            "trigger": fields.get("trigger", ""),
            "when": fields.get("when", ""),
            "content": fields.get("content", ""),
            "timezone_name": DEFAULT_SCHEDULE_TIMEZONE,
        }
