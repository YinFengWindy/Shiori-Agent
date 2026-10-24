from __future__ import annotations

from dataclasses import replace
from types import MappingProxyType

from shiori_sdk import PluginRuntimeContext
from shiori_sdk.core.conversation import StepFinished


async def stop_at_hard_limit(event: StepFinished) -> StepFinished:
    """Requests a summary once an unfinished step reaches the request hard limit.

    The threshold is the current model's unified-budget hard input limit,
    ``StepFinished.input_limit_tokens``. Below it the next request is still
    sendable and crossing the compaction trigger is handled by request
    compaction; at or above it continuing to call tools cannot be sent as-is,
    so the loop wraps up. Without a model budget the step goes on.
    """
    limit = event.input_limit_tokens
    tokens = event.context_tokens_estimate
    if not event.has_more or limit is None or tokens < limit:
        return event
    return replace(
        event,
        early_stop=True,
        early_stop_reason="context_pressure",
        extra_metadata=MappingProxyType(
            {
                **event.extra_metadata,
                "context_pressure_tokens": tokens,
                "context_pressure_threshold": limit,
            }
        ),
    )


async def setup(ctx: "PluginRuntimeContext") -> None:
    """装配 context_pressure：在 StepFinished 上请求收尾。"""
    ctx.on(StepFinished, stop_at_hard_limit)
