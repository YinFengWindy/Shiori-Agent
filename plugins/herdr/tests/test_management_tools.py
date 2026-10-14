"""Chat reads and mutations cannot forge another role or bypass current attachment."""

import importlib
import importlib.util
import json
import sys

import pytest

from plugins.herdr.backend.management_tools import TaskManagementTool
from plugins.herdr.backend.models import CodingTask
from plugins.herdr.backend.service import TaskService
from shiori_sdk.testing.background_results import FakeBackgroundResultTarget
from shiori_sdk.testing.packages import plugin_directory
from shiori_sdk.testing.service_context import FakeServiceContext


async def test_list_filters_by_host_role_and_fake_arguments_do_not_change_it(tmp_path):
    context = FakeServiceContext("herdr", tmp_path)
    service = TaskService(tmp_path, context.processes)
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
    context.tools.context = {"role_id": "role-a"}
    tool = TaskManagementTool(
        service,
        context.tools,
        context.process_resources,
        "list",
        context.background_results,
    )
    listed = json.loads(await tool.execute(role_id="role-b"))["tasks"]
    assert [task["role_id"] for task in listed] == ["role-a"]
    context.process_resources.active = False
    with pytest.raises(RuntimeError, match="配置已替换"):
        await tool.execute()
    await context.aclose()


async def test_mutation_requires_authenticated_user_even_with_current_role(tmp_path):
    context = FakeServiceContext("herdr", tmp_path)
    context.tools.context = {"role_id": "role-a"}
    service = TaskService(tmp_path, context.processes)
    tool = TaskManagementTool(
        service,
        context.tools,
        context.process_resources,
        "continue",
        context.background_results,
    )
    with pytest.raises(PermissionError):
        await tool.execute(task_id="unknown", requirement="new")
    await context.aclose()


@pytest.fixture
def generations():
    """Import real plugin code twice, as independent runtime generations do."""
    directory = plugin_directory("herdr") / "backend"
    namespaces = ("herdr_test_retired", "herdr_test_current")
    modules = []
    try:
        for namespace in namespaces:
            spec = importlib.util.spec_from_file_location(
                namespace,
                directory / "__init__.py",
                submodule_search_locations=[str(directory)],
            )
            assert spec is not None and spec.loader is not None
            package = importlib.util.module_from_spec(spec)
            sys.modules[namespace] = package
            spec.loader.exec_module(package)
            modules.append(
                {
                    name: importlib.import_module(f"{namespace}.{name}")
                    for name in (
                        "cli",
                        "config",
                        "models",
                        "service",
                        "management_tools",
                    )
                }
            )
        # Retirement removes old imports, while the process owner keeps its
        # service alive. No management operation may re-import that namespace.
        for name in tuple(sys.modules):
            if name == namespaces[0] or name.startswith(namespaces[0] + "."):
                del sys.modules[name]
        yield modules
    finally:
        for name in tuple(sys.modules):
            if any(
                name == prefix or name.startswith(prefix + ".") for prefix in namespaces
            ):
                del sys.modules[name]


@pytest.mark.parametrize("action", ["get", "continue", "cancel"])
async def test_current_tools_manage_retained_service_across_import_namespaces(
    tmp_path, monkeypatch, generations, action
):
    retired, current = generations
    assert retired["cli"].CommandError is not current["cli"].CommandError
    context = FakeServiceContext("herdr", tmp_path)
    context.tools.context = {"role_id": "role-a"}
    target = FakeBackgroundResultTarget("role-a", "thread-a")
    context.background_results.target = target
    service = retired["service"].TaskService(tmp_path, context.processes)
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
        context.tools,
        context.process_resources,
        action,
        context.background_results,
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
