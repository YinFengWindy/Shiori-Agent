"""Wrap one remote MCP tool as a local tool. The server name is stored here."""

from __future__ import annotations

from typing import Any

from shiori_sdk.mcp import McpSession, McpToolInfo
from shiori_sdk.tools import Tool, ToolResult


class McpToolWrapper(Tool):
    """One remote tool. The name is ``mcp_{server}__{tool}``."""

    def __init__(self, server: str, session: McpSession, info: McpToolInfo) -> None:
        self._server = server
        self._session = session
        self._info = info

    @property
    def name(self) -> str:
        return f"mcp_{self._server}__{self._info.name}"

    @property
    def description(self) -> str:
        return f"[MCP:{self._server}] {self._info.description}"

    @property
    def parameters(self) -> dict[str, Any]:
        return dict(self._info.input_schema)

    async def execute(self, **kwargs: Any) -> str | ToolResult:
        return await self._session.call(self._info.name, kwargs)
