"""Chat reads and mutations cannot forge another role or bypass current attachment."""

import json

import pytest

from plugins.herdr.backend.management_tools import TaskManagementTool
from plugins.herdr.backend.models import CodingTask
from plugins.herdr.backend.service import TaskService
from shiori_sdk.testing.background_results import FakeBackgroundResultTarget
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
