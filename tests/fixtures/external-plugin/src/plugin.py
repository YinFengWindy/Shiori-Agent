"""Observable external lifecycle fixture using host-provided capabilities."""

from agent.tools.base import Tool
from bus.events_lifecycle import RoleDeleted

VERSION = "__FIXTURE_VERSION__"


class FixtureTool(Tool):
    """Prove tool registration through its real registry and execution contract."""

    name = "external_demo_probe"
    description = "Inspect the external lifecycle fixture"
    parameters = {"type": "object", "properties": {}}

    async def execute(self, **kwargs):
        """Return the independently built package version without external APIs."""
        return f"external tool {VERSION}"


async def setup(ctx):
    """Own observable resources and keep user data across code replacement."""
    ctx.kv.set("loads", ctx.kv.get("loads", 0) + 1)
    ctx.kv.set("version", VERSION)

    def disposed():
        ctx.kv.set(
            "backend_teardown",
            {
                "version": VERSION,
                "tool_absent": ctx.tools.get_tool(FixtureTool.name) is None,
            },
        )

    # Registered first: this runs after the later tool registration is revoked.
    ctx.effect("fixture_audit", disposed)
    ctx.tools.register(FixtureTool(), risk="read-only", always_on=True)

    def role_deleted(_event):
        ctx.kv.set("role_events", ctx.kv.get("role_events", 0) + 1)

    ctx.events.on(RoleDeleted, role_deleted)

    async def inspect(_payload):
        tool = ctx.tools.get_tool(FixtureTool.name)
        return {
            "version": VERSION,
            "tool": await tool.execute(),
            "saved": ctx.kv.get("saved", ""),
            "loads": ctx.kv.get("loads", 0),
            "role_events": ctx.kv.get("role_events", 0),
        }

    async def save(payload):
        ctx.kv.set("saved", str(payload["value"]))
        return await inspect({})

    async def pulse(_payload):
        await ctx.rpc.emit("pulse", {"version": VERSION})
        return {"version": VERSION}

    ctx.rpc.register("inspect", inspect)
    ctx.rpc.register("save", save)
    ctx.rpc.register("pulse", pulse)
