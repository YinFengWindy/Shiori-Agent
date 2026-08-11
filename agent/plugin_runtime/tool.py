from __future__ import annotations

from typing import Any

from agent.mcp.client import McpClient, McpToolInfo
from agent.plugin_packages.contracts import PluginToolDeclaration
from agent.tools.base import Tool


class PluginMcpTool(Tool):
    """Exposes one manifest-allowlisted plugin MCP tool to the Agent runtime."""

    def __init__(
        self,
        client: McpClient,
        info: McpToolInfo,
        declaration: PluginToolDeclaration,
        *,
        plugin_name: str,
    ) -> None:
        self._client = client
        self._info = info
        self._declaration = declaration
        self._plugin_name = plugin_name

    @property
    def name(self) -> str:
        return self._declaration.name

    @property
    def description(self) -> str:
        return f"[{self._plugin_name}] {self._info.description}".strip()

    @property
    def parameters(self) -> dict[str, Any]:
        return self._info.input_schema

    async def execute(self, **kwargs: Any) -> str:
        """Forwards one tool call to the isolated plugin MCP process."""

        return await self._client.call(self._declaration.remote_name, kwargs)
