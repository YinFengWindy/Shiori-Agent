"""Role-owned screen observation tool."""

from __future__ import annotations

import json
from typing import Any, Protocol

from agent.tools.base import Tool


class ScreenCapture(Protocol):
    """Captures one primary-screen frame for a specific role context."""

    def capture(self, role_id: str) -> dict[str, Any]: ...


class ScreenAnalyzer(Protocol):
    """Produces a validated, observation-only result for one frame."""

    async def analyze(self, payload: dict[str, Any]) -> dict[str, Any]: ...


class ObserveScreenTool(Tool):
    """Lets the active role inspect a primary-screen snapshot."""

    name = "observe_screen"
    context_precedence = frozenset({"role_id"})
    description = (
        "查看当前角色可观察的主屏幕，并返回界面与活动摘要。"
        "仅用于只读观察，不能点击、输入、滚动或执行任何屏幕操作。"
    )
    parameters = {
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    }

    def __init__(self, *, capture: ScreenCapture, analyzer: ScreenAnalyzer) -> None:
        self._capture = capture
        self._analyzer = analyzer

    async def execute(
        self,
        *,
        role_id: str = "",
        **_: Any,
    ) -> str:
        """Captures and analyzes one frame without exposing image bytes to the role."""

        clean_role_id = str(role_id or "").strip()
        if not clean_role_id:
            raise ValueError("当前会话缺少角色身份，无法观察屏幕")
        result = await self._analyzer.analyze(self._capture.capture(clean_role_id))
        return json.dumps(_safe_tool_result(result), ensure_ascii=False)


def _safe_tool_result(result: dict[str, Any]) -> dict[str, Any]:
    """Returns the small role-facing observation contract."""

    return {
        "available": True,
        "interface_summary": str(result.get("interface_summary") or "当前桌面活动"),
        "activity_key": str(result.get("activity_key") or "desktop-activity"),
    }
