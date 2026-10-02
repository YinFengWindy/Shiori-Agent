"""Host fixture with scoped lifecycle subscriptions."""

from agent.lifecycle.types import BeforeTurnCtx
from shiori_sdk.lifecycle import AfterStepCtx

after_step_calls: list[str] = []


async def before_turn(event):
    event.extra_metadata["hello_touched"] = True
    return event


async def after_step(event):
    after_step_calls.append(event.session_key)


async def setup(ctx):
    """Registers both handlers in the plugin effect scope."""
    ctx.events.on(BeforeTurnCtx, before_turn)
    ctx.events.on(AfterStepCtx, after_step)
