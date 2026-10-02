"""Host tool wrappers cannot redirect session ownership or screenshot output."""

from unittest.mock import AsyncMock


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
