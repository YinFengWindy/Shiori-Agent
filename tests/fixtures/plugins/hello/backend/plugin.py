"""Host fixture with a scoped event subscription."""

from agent.lifecycle.types import BeforeTurnCtx
from shiori_sdk.core.services import EVENTS


async def before_turn(event):
    event.extra_metadata["hello_touched"] = True
    return event


async def setup(ctx):
    """Registers the handler in the plugin effect scope."""
    ctx.require(EVENTS).on(BeforeTurnCtx, before_turn)
