"""Pinned, narrow Computer Use schemas with host-owned routing and lifecycle."""

import json
from pathlib import Path
from typing import Any

from agent.tools.base import Tool, ToolResult

from .desktop import ComputerDesktop

_FORBIDDEN = {
    "session",
    "scope",
    "target",
    "screenshot_out_file",
    "from_zoom",
    "socket",
    "command",
    "extraArgs",
}


def computer_tools(desktop: ComputerDesktop) -> list["ComputerTool"]:
    """Loads offline schemas captured from the fixed Cua Driver 0.28.2 binary."""
    specs = json.loads(
        Path(__file__).with_name("tools.json").read_text(encoding="utf-8")
    )
    return [ComputerTool(desktop, spec) for spec in specs]


class ComputerTool(Tool):
    """Routes exact window operations without exposing Driver administration."""

    context_precedence = frozenset({"role_id"})

    def __init__(self, desktop: ComputerDesktop, spec: dict[str, Any]) -> None:
        self._desktop, self._spec = desktop, spec

    @property
    def name(self) -> str:
        return "computer_" + self._spec["name"]

    @property
    def description(self) -> str:
        return "[Computer Use] " + self._spec["description"]

    @property
    def parameters(self) -> dict[str, Any]:
        return self._spec["inputSchema"]

    async def execute(self, *, role_id: str = "", **kwargs: Any) -> str | ToolResult:
        """Uses a non-forgeable host turn and rejects alternate coordinate/routing scopes."""
        if _FORBIDDEN.intersection(kwargs):
            raise ValueError(
                "Computer Use 仅支持显式窗口目标；会话、路径和进程由宿主管理，不支持桌面或其他显示器目标"
            )
        arguments = {
            key: value
            for key, value in kwargs.items()
            if key in self.parameters["properties"]
        }
        errors = self.validate_params(arguments)
        if errors:
            raise ValueError("；".join(errors))
        return await self._desktop.call(role_id, self._spec["name"], arguments)
