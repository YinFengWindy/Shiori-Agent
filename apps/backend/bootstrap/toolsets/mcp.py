"""The ``mcp`` toolset name remains resolvable for old configs.

MCP tools now come from the ``mcp`` plugin. Listing ``mcp`` here registers nothing.
"""

from __future__ import annotations

import logging

from agent.tools.registry import ToolRegistry
from bootstrap.toolsets.protocol import ToolsetDeps, ToolsetRegistrationResult

logger = logging.getLogger(__name__)


class McpToolsetProvider:
    """Accepts a legacy ``mcp`` toolset without registering host tools."""

    def register(
        self, registry: ToolRegistry, deps: ToolsetDeps
    ) -> ToolsetRegistrationResult:
        logger.info("toolset mcp 已由插件 mcp 提供，核心不再注册 MCP 工具")
        return ToolsetRegistrationResult(source_name="mcp")
