"""Plugin setup is lazy and only authenticated task capture can originate work."""

import pytest

from shiori_sdk.testing.service_context import FakeServiceContext
from plugins.herdr.backend.plugin import setup
from plugins.herdr.backend.service import TaskService


async def test_setup_uses_public_capabilities_without_starting_processes(tmp_path):
    context = FakeServiceContext("herdr", tmp_path)
    await setup(context.as_capability())
    assert isinstance(context.exported, TaskService)
    assert context.exported.tasks == {}
    tool = context.tools.tools["herdr_start_task"]
    with pytest.raises(PermissionError):
        await tool.execute(
            repository=str(tmp_path), requirement="fix", role_id="forged"
        )
    assert context.exported.tasks == {}
    await context.aclose()
