from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from agent.scheduler import SchedulerService
from bus.event_bus import EventBus
from core.roles import RoleStore
from desktop_bridge.service import DesktopBridgeService
from session.manager import SessionManager


@pytest.mark.asyncio
async def test_desktop_bridge_lists_and_cancels_role_subagent_tasks(tmp_path):
    role_store = RoleStore(tmp_path)
    role_store.create_role(
        role_id="mira",
        name="Mira",
        description="",
        system_prompt="you are mira",
    )
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

    async def cancel(job_id: str) -> bool:
        jobs[:] = [job for job in jobs if job["job_id"] != job_id]
        return True

    manager = SimpleNamespace(
        list_running_jobs=lambda: list(jobs),
        cancel=AsyncMock(side_effect=cancel),
    )
    service = DesktopBridgeService(
        workspace=tmp_path,
        role_store=role_store,
        session_manager=SessionManager(tmp_path),
        agent_loop=SimpleNamespace(process_direct=AsyncMock()),
        event_bus=EventBus(),
        subagent_manager=manager,
    )

    listed = await service.handle(
        {"id": "1", "method": "roles.tasks.list", "payload": {"role_id": "mira"}},
        emit_event=lambda payload: None,
    )
    cancelled = await service.handle(
        {
            "id": "2",
            "method": "roles.tasks.cancel",
            "payload": {"role_id": "mira", "task_id": "subagent-a"},
        },
        emit_event=lambda payload: None,
    )

    assert [task["id"] for task in listed.payload["tasks"]] == ["subagent-a"]
    manager.cancel.assert_awaited_once_with("subagent-a")
    assert cancelled.payload["tasks"] == []


@pytest.mark.asyncio
async def test_desktop_bridge_creates_updates_and_emits_role_task_events(tmp_path):
    role_store = RoleStore(tmp_path)
    role_store.create_role(
        role_id="mira",
        name="Mira",
        description="",
        system_prompt="you are mira",
    )
    scheduler = SchedulerService(
        store_path=tmp_path / "schedules.json",
        push_tool=SimpleNamespace(execute=AsyncMock()),
        agent_loop=SimpleNamespace(process_direct=AsyncMock()),
    )
    service = DesktopBridgeService(
        workspace=tmp_path,
        role_store=role_store,
        session_manager=SessionManager(tmp_path),
        agent_loop=SimpleNamespace(process_direct=AsyncMock()),
        event_bus=EventBus(),
        scheduler=scheduler,
    )
    events = []

    created = await service.handle(
        {
            "id": "create",
            "method": "roles.tasks.create",
            "payload": {
                "role_id": "mira",
                "name": "喝水",
                "tier": "instant",
                "trigger": "after",
                "when": "30m",
                "content": "记得喝水",
            },
        },
        emit_event=events.append,
    )
    task_id = created.payload["task"]["id"]
    updated = await service.handle(
        {
            "id": "update",
            "method": "roles.tasks.update",
            "payload": {
                "role_id": "mira",
                "task_id": task_id,
                "name": "天气",
                "tier": "soft",
                "trigger": "every",
                "when": "0 9 * * *",
                "content": "查询天气",
            },
        },
        emit_event=events.append,
    )

    assert created.error is None
    assert updated.error is None
    assert updated.payload["task"]["schedule"]["content"] == "查询天气"
    assert scheduler.list_jobs()[0].channel == "desktop"
    assert scheduler.list_jobs()[0].chat_id == "role:mira"
    assert [event["method"] for event in events] == [
        "roles.tasks.updated",
        "roles.tasks.updated",
    ]
    assert all(event["payload"] == {"role_id": "mira"} for event in events)


@pytest.mark.asyncio
async def test_desktop_bridge_rejects_cross_role_and_running_schedule_updates(tmp_path):
    role_store = RoleStore(tmp_path)
    for role_id in ("mira", "other"):
        role_store.create_role(
            role_id=role_id,
            name=role_id,
            description="",
            system_prompt=f"you are {role_id}",
        )
    scheduler = SchedulerService(
        store_path=tmp_path / "schedules.json",
        push_tool=SimpleNamespace(execute=AsyncMock()),
        agent_loop=SimpleNamespace(process_direct=AsyncMock()),
    )
    job = scheduler.create_job(
        name="喝水",
        tier="instant",
        trigger="after",
        when="30m",
        content="记得喝水",
        timezone_name="UTC",
        channel="desktop",
        chat_id="role:mira",
        role_id="mira",
    )
    service = DesktopBridgeService(
        workspace=tmp_path,
        role_store=role_store,
        session_manager=SessionManager(tmp_path),
        agent_loop=SimpleNamespace(process_direct=AsyncMock()),
        event_bus=EventBus(),
        scheduler=scheduler,
    )
    update_payload = {
        "task_id": job.id,
        "name": "新名称",
        "tier": "instant",
        "trigger": "after",
        "when": "1h",
        "content": "新内容",
    }

    cross_role = await service.handle(
        {"id": "cross", "method": "roles.tasks.update", "payload": {**update_payload, "role_id": "other"}},
        emit_event=lambda payload: None,
    )
    scheduler._in_flight.add(job.id)
    running = await service.handle(
        {"id": "running", "method": "roles.tasks.update", "payload": {**update_payload, "role_id": "mira"}},
        emit_event=lambda payload: None,
    )

    assert cross_role.error is not None
    assert running.error is not None
    assert scheduler.list_jobs()[0].name == "喝水"
