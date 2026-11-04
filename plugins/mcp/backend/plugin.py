"""Assemble inert MCP management; connections begin only after publication."""

import asyncio

from shiori_sdk.storage import plugin_data_dir
from shiori_sdk.core.mcp_tools import MCP_TOOLS
from shiori_sdk.core.services import (
    BACKGROUND,
    PROCESSES,
    TOOLS,
    WORKSPACE,
    RPC,
    PROCESS_RESOURCES,
)
from shiori_sdk.runtime import PluginRuntimeContext
from .manage_tools import McpAddTool, McpListTool, McpRemoveTool
from .registry import McpServerRegistry
from .rpc import McpManagement


async def setup(ctx: PluginRuntimeContext) -> None:
    """Publish one owner shared by desktop, chat and declared source consumers."""
    resources = ctx.require(PROCESS_RESOURCES)
    background = ctx.require(BACKGROUND)
    changed_event = asyncio.Event()
    published_event = asyncio.Event()

    async def emit_changes():
        while True:
            await changed_event.wait()
            changed_event.clear()
            if resources.active:
                await ctx.require(RPC).emit("servers.changed", {})

    def changed():
        changed_event.set()

    registry = McpServerRegistry(
        plugin_data_dir(ctx.require(WORKSPACE), "mcp") / "mcp_servers.json",
        processes=ctx.require(PROCESSES),
        registration=ctx.require(MCP_TOOLS),
        changed=changed,
        active=lambda: resources.active,
    )
    ctx.expose(registry)
    tools = ctx.require(TOOLS)
    tools.register(McpAddTool(registry), risk="external-side-effect")
    tools.register(McpRemoveTool(registry), risk="write")
    tools.register(McpListTool(registry), risk="read-only")
    McpManagement(registry).register(ctx)
    ctx.effect("mcp.shutdown", registry.shutdown)

    async def connect_published():
        await published_event.wait()
        await registry.load_and_connect_all()

    # Register deterministic lifetimes during setup. Publication only opens the
    # latch; candidates never touch files or spawn a server before publication.
    background.spawn(emit_changes(), name="mcp-status")
    background.spawn(connect_published(), name="mcp-connect")
    ctx.effect("mcp.publication", resources.on_published(published_event.set))
