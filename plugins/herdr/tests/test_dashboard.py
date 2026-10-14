"""Desktop global read/control and generation-scoped event lifetime."""

import asyncio
from unittest.mock import AsyncMock

import pytest

from plugins.herdr.backend.dashboard import Dashboard
from plugins.herdr.backend.models import CodingTask
from plugins.herdr.backend.service import TaskService
from plugins.herdr.backend.management_tools import TaskManagementTool
from shiori_sdk.testing.background_results import FakeBackgroundResultTarget
from shiori_sdk.testing.service_context import FakeServiceContext
from shiori_sdk.rpc import Concurrency


@pytest.fixture
def fixture(tmp_path):
    ctx = FakeServiceContext("herdr", tmp_path)
    service = TaskService(tmp_path, ctx.processes)
    dashboard = Dashboard(service, ctx.as_capability())
    dashboard.register()
    for role in ("role-a", "role-b"):
        service.tasks[role] = CodingTask(
            role,
            "task",
            tmp_path,
            "codex",
            FakeBackgroundResultTarget(role, "thread"),
            tmp_path,
            "branch",
            "run",
        )
    return ctx, service, dashboard


async def test_snapshot_is_global_but_role_tool_remains_scoped(fixture):
    ctx, service, dashboard = fixture
    snapshot = await dashboard.snapshot({})
    assert len(snapshot["tasks"]) == 2
    assert ctx.rpc.concurrency["tasks.snapshot"] is Concurrency.READ_ONLY
    ctx.tools.context = {"role_id": "role-a"}
    tool = TaskManagementTool(
        service, ctx.tools, ctx.process_resources, "get", ctx.background_results
    )
    with pytest.raises(ValueError, match="当前角色"):
        await tool.execute(task_id="role-b")
    await ctx.aclose()


async def test_candidate_does_not_emit_and_disposal_removes_subscription(fixture):
    ctx, service, _ = fixture
    ctx.process_resources.active = False
    service.changed(service.tasks["role-a"])
    await asyncio.sleep(0)
    assert ctx.rpc.events == []
    ctx.process_resources.active = True
    service.changed(service.tasks["role-a"])
    await asyncio.sleep(0)
    assert ctx.rpc.events == [("tasks.changed", {"task_id": "role-a", "revision": 2})]
    await ctx.aclose()
    service.changed(service.tasks["role-a"])
    await asyncio.sleep(0)
    assert len(ctx.rpc.events) == 1


async def test_desktop_action_uses_task_owner_and_shared_operation(
    fixture, monkeypatch
):
    ctx, service, dashboard = fixture
    operation = AsyncMock(return_value=service.tasks["role-b"])
    monkeypatch.setattr("plugins.herdr.backend.dashboard.continue_task", operation)
    await dashboard.continue_task(
        {"task_id": "role-b", "role_id": "forged", "requirement": "追加要求"}
    )
    operation.assert_awaited_once_with(service, "role-b", "追加要求", "role-b")
    ctx.process_resources.active = False
    with pytest.raises(RuntimeError, match="配置已替换"):
        await dashboard.cancel_task({"task_id": "role-a"})
    await ctx.aclose()
