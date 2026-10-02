from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from plugins.screen_perception.backend.tool import ObserveScreenTool
from agent.tools.registry import ToolRegistry


@pytest.mark.asyncio
async def test_observe_screen_uses_the_current_role_context_over_tool_arguments() -> (
    None
):
    capture = SimpleNamespace(capture=Mock(return_value={"role_id": "mira"}))
    analyzer = SimpleNamespace(analyze=AsyncMock(return_value={}))
    registry = ToolRegistry()
    registry.register(ObserveScreenTool(capture=capture, analyzer=analyzer))

    await registry.execute(
        "observe_screen",
        {"role_id": "other"},
        context={"channel": "telegram", "role_id": "mira"},
    )

    capture.capture.assert_called_once_with("mira")
