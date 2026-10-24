"""Host fixture with a scoped event subscription."""

from agent.lifecycle.types import BeforeTurnCtx


async def before_turn(event):
    event.extra_metadata["hello_touched"] = True
    return event


async def setup(ctx):
    """Registers the handler in the plugin effect scope."""
    ctx.events.on(BeforeTurnCtx, before_turn)
