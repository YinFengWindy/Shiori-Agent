"""Host registration of dynamic MCP tools.

``ToolsCapability.register`` cannot set ``source_type``. Drift still groups
these tools by ``source_type="mcp"`` and the server name, so the host writes
that metadata here.
"""

from __future__ import annotations

from shiori_sdk.tools import Tool

from agent.tools.registry import ToolRegistry


class HostMcpToolRegistration:
    """``MCP_TOOLS`` over one generation's tool registry."""

    def __init__(self, registry: ToolRegistry) -> None:
        self._registry = registry

    def add(
        self, tool: Tool, *, server: str, risk: str = "external-side-effect"
    ) -> None:
        """Register ``tool`` as an MCP tool of ``server``."""
        self._registry.register(tool, risk=risk, source_type="mcp", source_name=server)

    def remove(self, name: str) -> None:
        """Drop a previously registered tool. Missing names are ignored."""
        self._registry.unregister(name)
