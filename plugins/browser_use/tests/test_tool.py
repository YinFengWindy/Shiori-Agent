"""Host tool wrappers cannot redirect session ownership or screenshot output."""

from unittest.mock import AsyncMock

import pytest

from plugins.browser_use.backend.tool import browser_tools


def test_versioned_tool_surface_hides_session_and_launch_overrides():
    tools = browser_tools(AsyncMock())
    assert len(tools) == 28
    for tool in tools:
        assert not {
            "session",
            "namespace",
            "extraArgs",
            "headed",
            "path",
            "all",
        }.intersection(tool.parameters["properties"])


async def test_role_identity_is_host_context_and_routing_overrides_are_refused():
    """Host context supplies the role; tool arguments cannot redirect the session."""
    sessions = AsyncMock()
    tool = next(t for t in browser_tools(sessions) if t.name == "agent_browser_fill")
    assert tool.context_precedence == frozenset({"role_id"})
    await tool.execute(
        role_id="actual",
        channel="desktop",
        chat_id="chat",
        selector="@e1",
        text="中文",
    )
    sessions.call.assert_awaited_once_with(
        "actual", tool.name, {"selector": "@e1", "text": "中文"}
    )
    with pytest.raises(ValueError, match="宿主管理"):
        await tool.execute(
            role_id="role", selector="@e1", text="中文", extraArgs=["--auto-connect"]
        )
