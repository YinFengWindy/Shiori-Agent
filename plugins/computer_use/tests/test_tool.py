"""The model cannot forge host identity or escape the supported window surface."""

from unittest.mock import AsyncMock


from plugins.computer_use.backend.tool import computer_tools


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
