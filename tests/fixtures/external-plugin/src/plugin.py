"""Observable external lifecycle fixture using host-provided capabilities."""

from shiori_sdk.core.services import EVENTS, KV, RPC, TOOLS
from shiori_sdk.role_events import RoleDeleted
from shiori_sdk.tools import Tool

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
    kv = ctx.require(KV)
    tools = ctx.require(TOOLS)
    events = ctx.require(EVENTS)
    rpc = ctx.require(RPC)
    kv.set("loads", kv.get("loads", 0) + 1)
    kv.set("version", VERSION)

    def disposed():
        kv.set(
            "backend_teardown",
            {
                "version": VERSION,
                "tool_absent": tools.get_tool(FixtureTool.name) is None,
            },
        )

    # Registered first: this runs after the later tool registration is revoked.
    ctx.effect("fixture_audit", disposed)
    tools.register(FixtureTool(), risk="read-only", always_on=True)

    def role_deleted(_event):
        kv.set("role_events", kv.get("role_events", 0) + 1)

    events.on(RoleDeleted, role_deleted)

    async def inspect(_payload):
        tool = tools.get_tool(FixtureTool.name)
        return {
            "version": VERSION,
            "tool": await tool.execute(),
            "saved": kv.get("saved", ""),
            "loads": kv.get("loads", 0),
            "role_events": kv.get("role_events", 0),
        }

    async def save(payload):
        kv.set("saved", str(payload["value"]))
        return await inspect({})

    async def pulse(_payload):
        await rpc.emit("pulse", {"version": VERSION})
        return {"version": VERSION}

    rpc.register("inspect", inspect)
    rpc.register("save", save)
    rpc.register("pulse", pulse)
