"""``MCP_TOOLS``: register a remote MCP tool with source metadata (P6a).

``ToolsCapability.register`` cannot grow a ``source_type`` parameter (D22).
Drift and search still group dynamic MCP tools by ``source_type="mcp"`` and
``source_name`` equal to the server. The host provides this key and writes
that metadata. The ``mcp`` plugin calls it. Manage tools (``mcp_add`` and
the rest) use ordinary ``TOOLS.register``.
"""

from __future__ import annotations

from typing import Protocol

from shiori_sdk.kernel import Key
from shiori_sdk.tools import Tool


class McpToolRegistration(Protocol):
    """Puts one remote tool in the host registry and takes it out again."""

    def add(
        self, tool: Tool, *, server: str, risk: str = "external-side-effect"
    ) -> None:
        """Register ``tool`` as an MCP tool of ``server``."""
        ...

    def remove(self, name: str) -> None:
        """Drop a previously registered tool. Missing names are ignored."""
        ...


MCP_TOOLS: Key[McpToolRegistration] = Key("mcp_tools")
"""MCP tool registration. The host provides this."""
