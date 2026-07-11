from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

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
