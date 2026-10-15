"""Desktop global read/control and generation-scoped event lifetime."""

import asyncio
import json
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


async def test_list_is_global_but_role_tool_remains_scoped(fixture):
    ctx, service, _ = fixture
    for name in ("tasks.list", "tasks.get"):
        assert ctx.rpc.concurrency[name] is Concurrency.READ_ONLY
    assert "tasks.snapshot" not in ctx.rpc.handlers
    listed = await ctx.rpc.handlers["tasks.list"]({})
    assert listed["instance_id"] == service.instance_id
    assert {task["id"] for task in listed["tasks"]} == {"role-a", "role-b"}
    ctx.tools.context = {"role_id": "role-a"}
    tool = TaskManagementTool(
        service, ctx.tools, ctx.process_resources, "get", ctx.background_results
    )
    with pytest.raises(ValueError, match="当前角色"):
        await tool.execute(task_id="role-b")
    await ctx.aclose()


async def test_list_summarizes_and_get_details_the_current_run(fixture, tmp_path):
    ctx, service, _ = fixture
    task = service.tasks["role-a"]
    task.requirement = "\n  修复滚动  \n第二行\n\n用户追加要求：\n再补测试"
    task.created_at = "2999-01-01T00:00:00+00:00"
    task.worktree, task.pane_id, task.status = tmp_path, "pane", "blocked"
    task.output = "x" * 20000
    # An older run's report written last must not stand in for this run's progress.
    task.progress_events = [
        {
            "run_id": "run",
            "stage": "implementation",
            "detail": "改滚动",
            "observed_at": "t2",
        },
        {"run_id": "old", "stage": "analysis", "detail": "旧回合", "observed_at": "t3"},
    ]
    task.stage = "implementation"

    listed = await ctx.rpc.handlers["tasks.list"]({})
    summary = listed["tasks"][0]
    assert summary == {
        "id": "role-a",
        "title": "修复滚动",
        "status": "blocked",
        "finished": False,
        "stage": "implementation",
        "progress_detail": "改滚动",
        "progress_updated_at": "t2",
        "role_id": "role-a",
        "agent": "codex",
        "repository": str(tmp_path),
        "branch": "branch",
        "created_at": task.created_at,
        "updated_at": task.updated_at,
        "revision": task.revision,
    }

    result = await ctx.rpc.handlers["tasks.get"]({"task_id": "role-a"})
    assert result["instance_id"] == service.instance_id
    detail = result["task"]
    assert {key: detail[key] for key in summary} == summary
    assert len(detail["output"]) == 16000
    assert [event["detail"] for event in detail["progress_events"]] == ["改滚动"]
    assert detail["requirement"] == task.requirement
    assert detail["worktree"] == str(tmp_path)
    assert detail["can_continue"] is True and detail["can_cancel"] is True

    for status, finished in [("unknown", False), ("failed", True), ("cancelled", True)]:
        task.status = status
        assert (await ctx.rpc.handlers["tasks.list"]({}))["tasks"][0][
            "finished"
        ] is finished

    with pytest.raises(ValueError, match="任务不存在"):
        await ctx.rpc.handlers["tasks.get"]({"task_id": "missing"})
    ctx.process_resources.active = False
    with pytest.raises(RuntimeError, match="配置已替换"):
        await ctx.rpc.handlers["tasks.list"]({})
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


@pytest.mark.parametrize("action", ["continue", "cancel"])
async def test_desktop_action_uses_task_owner_and_shared_operation(
    fixture, monkeypatch, action
):
    ctx, service, dashboard = fixture
    operation = AsyncMock(return_value=service.tasks["role-b"])
    monkeypatch.setattr(service, f"{action}_task", operation)
    await ctx.rpc.handlers[f"tasks.{action}"](
        {"task_id": "role-b", "role_id": "forged", "requirement": "追加要求"}
    )
    if action == "continue":
        operation.assert_awaited_once_with("role-b", "追加要求", "role-b")
    else:
        operation.assert_awaited_once_with("role-b", "role-b")
    ctx.process_resources.active = False
    with pytest.raises(RuntimeError, match="配置已替换"):
        await dashboard.cancel_task({"task_id": "role-a"})
    await ctx.aclose()


@pytest.mark.parametrize("action", ["continue", "cancel"])
async def test_current_rpc_namespace_uses_retained_owners_operations(
    tmp_path, monkeypatch, generations, action
):
    retired, current = generations
    assert retired["cli"].CommandError is not current["cli"].CommandError
    ctx = FakeServiceContext("herdr", tmp_path)
    target = FakeBackgroundResultTarget("role-a", "thread-a")
    service = retired["service"].TaskService(tmp_path, ctx.processes)
    task = retired["models"].CodingTask(
        "task-a",
        "original",
        tmp_path,
        "codex",
        target,
        tmp_path,
        "codex/task",
        "run-a",
        worktree=tmp_path,
        pane_id="owned-pane",
        agent_name="owned-agent",
        status="blocked",
        config=retired["config"].HerdrConfig(session="original"),
    )
    service.tasks[task.id] = task

    async def command(cli, argv, **kwargs):
        assert cli.config.session == "original"
        return json.dumps(
            {
                "result": {
                    "agent": {
                        "agent": "codex",
                        "agent_status": "idle",
                        "pane_id": "owned-pane",
                    }
                }
            }
        )

    async def execute(current_task, *, continuing):
        assert current_task is task and continuing
        current_task.touch("blocked")

    monkeypatch.setattr(retired["cli"].HerdrCli, "command", command)
    monkeypatch.setattr(service, "_execute", execute)
    operation = AsyncMock(wraps=getattr(service, f"{action}_task"))
    monkeypatch.setattr(service, f"{action}_task", operation)
    dashboard = current["dashboard"].Dashboard(service, ctx.as_capability())
    dashboard.register()
    try:
        result = await ctx.rpc.handlers[f"tasks.{action}"](
            {
                "task_id": task.id,
                "requirement": "new requirement",
                "role_id": "forged",
            }
        )
        snapshot = result["task"]
        assert isinstance(snapshot, dict)
        assert snapshot["id"] == task.id
        assert task.worker is not None
        await task.worker
        if action == "continue":
            operation.assert_awaited_once_with(task.id, "new requirement", "role-a")
            assert task.run_id != "run-a"
            assert task.requirement.endswith("new requirement")
        else:
            operation.assert_awaited_once_with(task.id, "role-a")
            assert task.status == "cancelled"
            assert [json.loads(text)["status"] for text in target.reports.values()] == [
                "cancelled"
            ]
    finally:
        await service.close()
        await ctx.aclose()
