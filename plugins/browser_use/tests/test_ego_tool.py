"""Malformed or redirected commands fail before touching a browser."""

from unittest.mock import AsyncMock

import pytest

from plugins.browser_use.backend.ego_tool import ego_tools


@pytest.mark.parametrize(
    "name,arguments",
    [
        ("actions", {"actions": [{"action": "fill", "selector": "@1"}]}),
        (
            "actions",
            {"actions": [{"action": "click", "selector": "@1", "script": "unsafe"}]},
        ),
        ("tabs", {"action": "close"}),
        ("open", {"url": "http://localhost", "spaceId": 1}),
        ("actions", {"actions": []}),
        ("actions", {"actions": [{"action": "click", "selector": "@1"}] * 33}),
    ],
)
async def test_invalid_commands_cannot_reach_the_browser(name, arguments):
    async def forbidden(*_, **__):
        pytest.fail("Invalid command reached the browser")

    manager = AsyncMock()
    manager.call.side_effect = forbidden
    tool = next(
        tool for tool in ego_tools(manager) if tool.name == "ego_browser_" + name
    )
    with pytest.raises(ValueError):
        await tool.execute(role_id="actual-role", **arguments)
