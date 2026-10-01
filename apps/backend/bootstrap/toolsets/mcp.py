from __future__ import annotations


from agent.mcp.manage_tools import McpAddTool, McpListTool, McpRemoveTool
from agent.mcp.registry import McpServerRegistry
from agent.tools.registry import ToolRegistry
from bootstrap.runtime.construction import track_build_resource
from bootstrap.toolsets.protocol import (
    ToolsetDeps,
    ToolsetProvider,
    build_registration_result,
)


class McpToolsetProvider(ToolsetProvider):
    def register(self, registry: ToolRegistry, deps: ToolsetDeps):
        before = set(registry._tools.keys())
        mcp_registry = McpServerRegistry(
            config_path=deps.workspace / "mcp_servers.json",
            tool_registry=registry,
        )
        track_build_resource(mcp_registry, mcp_registry.shutdown)
        registry.register(McpAddTool(mcp_registry), risk="external-side-effect")
        registry.register(McpRemoveTool(mcp_registry), risk="write")
        registry.register(McpListTool(mcp_registry), risk="read-only")
        return build_registration_result(
            registry=registry,
            source_name="mcp",
            before=before,
            extras={"mcp_registry": mcp_registry},
        )
