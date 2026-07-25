from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from agent.tools.observe_screen import ObserveScreenTool
from agent.tools.registry import ToolRegistry


def test_observe_screen_description_matches_role_owned_availability() -> None:
    assert "屏幕观察已开启" not in ObserveScreenTool.description
    assert "桌宠" not in ObserveScreenTool.description
    assert "界面与活动摘要" in ObserveScreenTool.description


@pytest.mark.asyncio
async def test_observe_screen_returns_only_the_safe_role_summary() -> None:
    capture = SimpleNamespace(
        capture=Mock(
            return_value={
                "role_id": "mira",
                "image_base64": "raw-frame-must-not-leak",
            }
        )
    )
    analyzer = AsyncMock(
        return_value={
            "interface_summary": "代码编辑器",
            "activity_key": "coding",
            "targets": [{"label": "private source", "x": 1, "y": 2}],
            "risks": [],
        }
    )
    tool = ObserveScreenTool(
        capture=capture,
        analyzer=SimpleNamespace(analyze=analyzer),
    )

    output = await tool.execute(channel="telegram", role_id="mira")

    assert json.loads(output) == {
        "available": True,
        "interface_summary": "代码编辑器",
        "activity_key": "coding",
    }
    capture.capture.assert_called_once_with("mira")
    analyzer.assert_awaited_once_with(capture.capture.return_value)
    assert "raw-frame" not in output


@pytest.mark.asyncio
async def test_observe_screen_returns_a_risky_screen_summary_to_the_role() -> None:
    analyzer = AsyncMock(
        return_value={
            "interface_summary": "包含密钥的窗口",
            "activity_key": "sensitive",
            "risks": ["credential"],
        }
    )
    tool = ObserveScreenTool(
        capture=SimpleNamespace(capture=Mock(return_value={"role_id": "mira"})),
        analyzer=SimpleNamespace(analyze=analyzer),
    )

    output = await tool.execute(channel="qq", role_id="mira")

    assert json.loads(output) == {
        "available": True,
        "interface_summary": "包含密钥的窗口",
        "activity_key": "sensitive",
    }


@pytest.mark.asyncio
async def test_observe_screen_rejects_calls_without_a_role() -> None:
    tool = ObserveScreenTool(
        capture=SimpleNamespace(capture=Mock()),
        analyzer=SimpleNamespace(analyze=AsyncMock()),
    )

    with pytest.raises(ValueError, match="缺少角色身份"):
        await tool.execute(channel="telegram")


@pytest.mark.asyncio
async def test_observe_screen_uses_the_current_role_context_over_tool_arguments() -> None:
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
