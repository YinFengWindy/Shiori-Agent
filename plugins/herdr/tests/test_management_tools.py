"""Chat reads and mutations cannot forge another role or bypass current attachment."""

from pathlib import Path
import json

import pytest

from plugins.herdr.backend.management_tools import TaskManagementTool
from plugins.herdr.backend.models import CodingTask
from plugins.herdr.backend.service import TaskService
from shiori_sdk.testing.background_results import FakeBackgroundResultTarget
from shiori_sdk.testing.service_context import FakeServiceContext

PACKAGE_DIR = Path(__file__).resolve().parents[1]


async def test_list_filters_by_host_role_and_fake_arguments_do_not_change_it(tmp_path):
    context = FakeServiceContext("herdr", tmp_path, package_dir=PACKAGE_DIR)
    service = TaskService(tmp_path)
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
    context.fake_tools.context = {"role_id": "role-a"}
    tool = TaskManagementTool(
        service,
        context.fake_tools,
        context.fake_process_resources,
        "list",
        context.fake_background_results,
    )
    listed = json.loads(await tool.execute(role_id="role-b"))["tasks"]
    assert [task["role_id"] for task in listed] == ["role-a"]
    context.fake_process_resources.active = False
    with pytest.raises(RuntimeError, match="配置已替换"):
        await tool.execute()
    await context.aclose()


async def test_mutation_requires_authenticated_user_even_with_current_role(tmp_path):
    context = FakeServiceContext("herdr", tmp_path, package_dir=PACKAGE_DIR)
    context.fake_tools.context = {"role_id": "role-a"}
    service = TaskService(tmp_path)
    tool = TaskManagementTool(
        service,
        context.fake_tools,
        context.fake_process_resources,
        "continue",
        context.fake_background_results,
    )
    with pytest.raises(PermissionError):
        await tool.execute(task_id="unknown", requirement="new")
    await context.aclose()


@pytest.mark.parametrize("action", ["get", "continue", "cancel"])
async def test_current_tools_manage_retained_service_across_import_namespaces(
    tmp_path, monkeypatch, generations, action
):
    retired, current = generations
    assert retired["cli"].CommandError is not current["cli"].CommandError
    context = FakeServiceContext("herdr", tmp_path, package_dir=PACKAGE_DIR)
    context.fake_tools.context = {"role_id": "role-a"}
    target = FakeBackgroundResultTarget("role-a", "thread-a")
    context.fake_background_results.target = target
    service = retired["service"].TaskService(tmp_path)
    service.attach(context.fake_process_resources, context.fake_processes, tmp_path)
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
    unavailable = True

    async def command(cli, argv, **kwargs):
        assert cli.config.session == "original"
        if unavailable:
            return json.dumps(
                {
                    "error": {
                        "code": "agent_not_found",
                        "message": "temporarily unavailable",
                    }
                }
            )
        if "read" in argv:
            return "current terminal output"
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

    async def execute(task, *, continuing):
        assert continuing
        task.touch("blocked")

    monkeypatch.setattr(retired["cli"].HerdrCli, "command", command)
    monkeypatch.setattr(service, "_execute", execute)
    tool = current["management_tools"].TaskManagementTool(
        service,
        context.fake_tools,
        context.fake_process_resources,
        action,
        context.fake_background_results,
    )
    try:
        if action == "continue":
            with pytest.raises(
                retired["cli"].CommandError, match="temporarily unavailable"
            ):
                await tool.execute(task_id=task.id, requirement="new requirement")
            assert task.run_id == "run-a"
        else:
            result = json.loads(await tool.execute(task_id=task.id))
            if action == "get":
                assert "当前终端状态不可读取" in result["output"]
                assert "temporarily unavailable" in result["output"]
                assert result["status"] == "blocked"
            else:
                await task.worker
                assert (
                    task.status == "unknown" and "temporarily unavailable" in task.error
                )

        unavailable = False
        result = json.loads(
            await tool.execute(task_id=task.id, requirement="new requirement")
        )
        if action == "get":
            assert result["output"] == "current terminal output"
            assert result["status"] == "blocked"
        elif action == "continue":
            await task.worker
            assert task.run_id != "run-a"
            assert task.requirement.endswith("new requirement")
        else:
            await task.worker
            assert task.status == "cancelled"
            assert [json.loads(text)["status"] for text in target.reports.values()] == [
                "unknown",
                "cancelled",
            ]
    finally:
        await service.close()
        await context.aclose()
