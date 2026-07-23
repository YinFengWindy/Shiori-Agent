from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from agent.tools.observe_screen import ObserveScreenTool


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

    output = await tool.execute(channel="desktop", role_id="mira")

    assert json.loads(output) == {
        "available": True,
        "interface_summary": "代码编辑器",
        "activity_key": "coding",
    }
    capture.capture.assert_called_once_with("mira")
    analyzer.assert_awaited_once_with(capture.capture.return_value)
    assert "raw-frame" not in output


@pytest.mark.asyncio
async def test_observe_screen_hides_a_risky_screen_from_the_role() -> None:
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

    output = await tool.execute(channel="desktop", role_id="mira")

    assert json.loads(output) == {
        "available": False,
        "reason": "screen_contains_sensitive_or_untrusted_content",
        "risks": ["credential"],
    }


@pytest.mark.asyncio
async def test_observe_screen_rejects_non_desktop_calls() -> None:
    tool = ObserveScreenTool(
        capture=SimpleNamespace(capture=Mock()),
        analyzer=SimpleNamespace(analyze=AsyncMock()),
    )

    with pytest.raises(ValueError, match="桌面角色会话"):
        await tool.execute(channel="telegram", role_id="mira")
