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
        self.last_create = None
        self.last_update = None

    def list_jobs(self):
        return list(self._jobs)

    def is_job_active(self, job_id: str) -> bool:
        return job_id in self._active_ids

    def cancel_job(self, job_id: str) -> bool:
        before = len(self._jobs)
        self._jobs = [job for job in self._jobs if job.id != job_id]
        return len(self._jobs) != before

    def create_job(self, **kwargs):
        self.last_create = kwargs
        job = _scheduled_job("created", kwargs["role_id"])
        job.name = kwargs["name"]
        job.tier = kwargs["tier"]
        job.trigger = kwargs["trigger"]
        job.when = kwargs["when"]
        job.message = kwargs["content"] if kwargs["tier"] == "instant" else None
        job.prompt = kwargs["content"] if kwargs["tier"] == "soft" else None
        job.timezone = kwargs["timezone_name"]
        self._jobs.append(job)
        return job

    def update_job(self, task_id: str, **kwargs):
        self.last_update = {"task_id": task_id, **kwargs}
        job = next(job for job in self._jobs if job.id == task_id)
        job.name = kwargs["name"]
        job.tier = kwargs["tier"]
        job.trigger = kwargs["trigger"]
        job.when = kwargs["when"]
        job.message = kwargs["content"] if kwargs["tier"] == "instant" else None
        job.prompt = kwargs["content"] if kwargs["tier"] == "soft" else None
        job.timezone = kwargs["timezone_name"]
        return job


def _scheduled_job(job_id: str, role_id: str):
    now = datetime(2026, 7, 11, 10, tzinfo=timezone.utc)
    return SimpleNamespace(
        id=job_id,
        role_id=role_id,
        name=f"job-{job_id}",
        message="提醒内容",
        prompt="",
        tier="instant",
        trigger="at",
        when="2026-07-11T18:00",
        timezone="Asia/Shanghai",
        interval_seconds=None,
        cron_expr=None,
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
    assert next(task for task in tasks if task["id"] == "schedule-a")["editable"] is False
    assert next(task for task in tasks if task["id"] == "schedule-a")["schedule"]["tier"] == "instant"
    assert next(task for task in tasks if task["kind"] == "memory_maintenance")["cancellable"] is False


def test_role_task_service_creates_and_updates_desktop_schedule_binding():
    scheduler = _Scheduler([])
    service = RoleTaskService(
        scheduler=scheduler,
        subagent_manager=None,
        memory_optimizer=None,
        session_key_for_role=lambda role_id: f"role:{role_id}",
    )

    created = service.create_schedule_task(
        "mira",
        name="提醒",
        tier="instant",
        trigger="after",
        when="30m",
        content="喝水",
    )
    updated = service.update_schedule_task(
        "mira",
        "created",
        name="天气",
        tier="soft",
        trigger="every",
        when="0 9 * * *",
        content="查看天气",
    )

    assert scheduler.last_create["channel"] == "desktop"
    assert scheduler.last_create["chat_id"] == "role:mira"
    assert scheduler.last_create["role_id"] == "mira"
    assert scheduler.last_create["timezone_name"] == "Asia/Shanghai"
    assert scheduler.last_update["timezone_name"] == "Asia/Shanghai"
    assert scheduler.last_update["role_id"] == "mira"
    assert created["schedule"]["content"] == "喝水"
    assert updated["schedule"]["tier"] == "soft"


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
