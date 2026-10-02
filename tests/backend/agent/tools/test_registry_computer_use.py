"""The model cannot forge host identity or escape the supported window surface."""

from unittest.mock import AsyncMock

import pytest

from agent.tools.registry import ToolRegistry
from plugins.computer_use.backend.tool import computer_tools


async def test_host_role_wins_and_desktop_routes_cannot_escape():
    desktop = AsyncMock()
    tool = next(
        tool for tool in computer_tools(desktop) if tool.name == "computer_type_text"
    )
    registry = ToolRegistry()
    registry.register(tool)
    args = {
        "pid": 42,
        "window_id": 81,
        "snapshot_id": "s00000001",
        "observation_id": "observation-1",
        "element_token": "s00000001:2",
        "text": "中文",
    }
    await registry.execute(
        tool.name,
        {**args, "role_id": "forged"},
        context={"role_id": "actual", "chat_id": "chat"},
    )
    desktop.call.assert_awaited_once_with("actual", "type_text", args)
    for key, value in {
        "session": "foreign",
        "target": {"kind": "desktop"},
        "scope": "desktop",
        "screenshot_out_file": "C:/out.png",
        "socket": "foreign",
    }.items():
        with pytest.raises(ValueError, match="宿主管理"):
            await tool.execute(role_id="role", **args, **{key: value})
