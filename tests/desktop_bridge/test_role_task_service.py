from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from desktop_bridge.role_task_service import RoleTaskService


class _Scheduler:
    def __init__(self, jobs, *, active_ids=()) -> None:
        self._jobs = list(jobs)
        self._active_ids = set(active_ids)

    def list_jobs(self):
        return list(self._jobs)

    def is_job_active(self, job_id: str) -> bool:
        return job_id in self._active_ids

    def cancel_job(self, job_id: str) -> bool:
        before = len(self._jobs)
        self._jobs = [job for job in self._jobs if job.id != job_id]
        return len(self._jobs) != before


def _scheduled_job(job_id: str, role_id: str):
    now = datetime(2026, 7, 11, 10, tzinfo=timezone.utc)
    return SimpleNamespace(
        id=job_id,
        role_id=role_id,
        name=f"job-{job_id}",
        message="提醒内容",
        prompt="",
        created_at=now,
        fire_at=now,
    )


def test_role_task_service_lists_only_tasks_owned_by_role():
    scheduler = _Scheduler(
        [_scheduled_job("schedule-a", "mira"), _scheduled_job("schedule-b", "other")],
        active_ids={"schedule-a"},
    )
    manager = SimpleNamespace(
        list_running_jobs=lambda: [
            {
                "job_id": "subagent-a",
                "label": "查资料",
                "task": "整理资料",
                "started_at": "2026-07-11T10:00:00+00:00",
                "status": "running",
                "origin_chat_id": "role:mira",
            },
            {
                "job_id": "subagent-b",
                "label": "其他角色任务",
                "task": "不应显示",
                "started_at": "2026-07-11T10:00:00+00:00",
                "status": "running",
                "origin_chat_id": "role:other",
            },
        ]
    )
    optimizer = SimpleNamespace(
        active_role_id="mira",
        active_started_at="2026-07-11T10:00:00+00:00",
    )
    service = RoleTaskService(
        scheduler=scheduler,
        subagent_manager=manager,
        memory_optimizer=optimizer,
        session_key_for_role=lambda role_id: f"role:{role_id}",
    )

    tasks = service.list_tasks("mira")

    assert {task["id"] for task in tasks} == {
        "schedule-a",
        "subagent-a",
        "memory-optimizer:mira",
    }
    assert {task["kind"] for task in tasks} == {
        "schedule",
        "subagent",
        "memory_maintenance",
    }
    assert next(task for task in tasks if task["id"] == "schedule-a")["status"] == "running"
    assert next(task for task in tasks if task["kind"] == "memory_maintenance")["cancellable"] is False


@pytest.mark.asyncio
async def test_role_task_service_cancels_only_matching_role_subagent():
    jobs = [
        {
            "job_id": "subagent-a",
            "label": "查资料",
            "task": "整理资料",
            "started_at": "2026-07-11T10:00:00+00:00",
            "status": "running",
            "origin_chat_id": "role:mira",
        }
    ]
    manager = SimpleNamespace(
        list_running_jobs=lambda: list(jobs),
        cancel=AsyncMock(return_value=True),
    )
    service = RoleTaskService(
        scheduler=None,
        subagent_manager=manager,
        memory_optimizer=None,
        session_key_for_role=lambda role_id: f"role:{role_id}",
    )

    with pytest.raises(KeyError, match="角色任务不存在"):
        await service.cancel_task("other", "subagent-a")
    manager.cancel.assert_not_awaited()

    await service.cancel_task("mira", "subagent-a")
    manager.cancel.assert_awaited_once_with("subagent-a")


@pytest.mark.asyncio
async def test_role_task_service_rejects_cross_role_schedule_cancellation():
    scheduler = _Scheduler([_scheduled_job("schedule-a", "mira")])
    service = RoleTaskService(
        scheduler=scheduler,
        subagent_manager=None,
        memory_optimizer=None,
        session_key_for_role=lambda role_id: f"role:{role_id}",
    )

    with pytest.raises(KeyError, match="角色任务不存在"):
        await service.cancel_task("other", "schedule-a")
    assert [job.id for job in scheduler.list_jobs()] == ["schedule-a"]
