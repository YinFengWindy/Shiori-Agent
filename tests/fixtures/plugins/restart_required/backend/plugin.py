"""A plugin that needs restart but still owns deterministic cleanup effects."""

from pydantic import BaseModel

from shiori_sdk.core.services import EVENTS


class RestartConfig(BaseModel):
    """A simple mutable value for config-channel regression tests."""

    value: str = "first"


async def setup(ctx):
    """Publishes lifecycle evidence while using a scoped subscription."""
    state = ["started"]

    async def on_event(event):
        return event

    ctx.require(EVENTS).on(str, on_event)
    ctx.effect("closed", lambda: state.append("closed"))
    ctx.expose(state)
