"""External MCP servers. Off until the user enables the plugin."""

from __future__ import annotations

from shiori_sdk.core.mcp_tools import MCP_TOOLS
from shiori_sdk.core.services import BACKGROUND, PROCESSES, TOOLS, WORKSPACE
from shiori_sdk.runtime import PluginRuntimeContext

from .manage_tools import McpAddTool, McpListTool, McpRemoveTool
from .registry import McpServerRegistry


async def setup(ctx: PluginRuntimeContext) -> None:
    """Registers manage tools and reconnects ``mcp_servers.json`` in the background."""
    registry = McpServerRegistry(
        ctx.require(WORKSPACE) / "mcp_servers.json",
        processes=ctx.require(PROCESSES),
        registration=ctx.require(MCP_TOOLS),
    )
    tools = ctx.require(TOOLS)
    tools.register(McpAddTool(registry), risk="external-side-effect")
    tools.register(McpRemoveTool(registry), risk="write")
    tools.register(McpListTool(registry), risk="read-only")
    ctx.require(BACKGROUND).spawn(registry.load_and_connect_all(), name="mcp-connect")

    async def shutdown() -> None:
        await registry.shutdown()

    ctx.effect("mcp.shutdown", shutdown)
