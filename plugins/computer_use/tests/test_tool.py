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


def test_tool_contract_requires_exact_target_and_snapshot_and_hides_admin():
    tools = computer_tools(AsyncMock())
    assert len(tools) == 8
    for tool in tools:
        props = tool.parameters["properties"]
        assert not {
            "session",
            "target",
            "scope",
            "screenshot_out_file",
            "from_zoom",
        }.intersection(props)
        if tool.name not in {"computer_list_windows", "computer_release"}:
            assert {"pid", "window_id"} <= set(tool.parameters["required"])
        if tool.name not in {
            "computer_list_windows",
            "computer_get_window_state",
            "computer_release",
        }:
            assert "snapshot_id" in tool.parameters["required"]
