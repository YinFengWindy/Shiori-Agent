"""Versioned MCP schemas with host-owned browser/session parameters."""

import json
from pathlib import Path
from typing import Any

from agent.tools.base import Tool, ToolResult

from .browser import BrowserSessions

# These upstream escape hatches are never model-controlled in this plugin.
_OWNED = frozenset(
    {
        "session",
        "namespace",
        "extraArgs",
        "headed",
        "all",
        "path",
        "screenshotDir",
        "restore",
        "restoreSave",
        "restoreCheckFn",
        "restoreCheckText",
        "restoreCheckUrl",
        "idleTimeout",
        "timeoutMs",
        "caCert",
        "clearCaCert",
        "allowedDomains",
        "webgpu",
        "webmcp",
    }
)


def browser_tools(sessions: BrowserSessions) -> list["BrowserTool"]:
    """Loads schemas captured from agent-browser v0.38.1 without starting a browser."""
    specs = json.loads(
        Path(__file__).with_name("tools.json").read_text(encoding="utf-8")
    )
    return [BrowserTool(sessions, spec) for spec in specs]


class BrowserTool(Tool):
    """Exposes a remote tool through the existing plugin discovery and image contract."""

    context_precedence = frozenset({"role_id"})

    def __init__(self, sessions: BrowserSessions, spec: dict[str, Any]) -> None:
        self._sessions, self._spec = sessions, spec

    @property
    def name(self) -> str:
        return self._spec["name"]

    @property
    def description(self) -> str:
        return (
            "[Browser Use] "
            + self._spec["description"]
            + " 当前角色独立浏览器；导航或引用失效后先snapshot重新观察。"
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return self._spec["inputSchema"]

    async def execute(self, *, role_id: str = "", **kwargs: Any) -> str | ToolResult:
        """Filters host context and rejects attempts to override owned session routing."""
        if _OWNED.intersection(kwargs):
            raise ValueError("Browser Use 会话、进程与截图路径由宿主管理")
        arguments = {
            key: value
            for key, value in kwargs.items()
            if key in self.parameters["properties"]
        }
        return await self._sessions.call(role_id, self.name, arguments)
