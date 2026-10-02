from __future__ import annotations

from shiori_sdk import PluginRuntimeContext
from shiori_sdk.lifecycle import AfterStepCtx, LifecycleFrame

_CTX_SLOT = "step:ctx"
_EARLY_STOP_REASON_SLOT = "step:early_stop_reason"
_TELEMETRY_PREFIX = "step:telemetry:"


class ContextPressureStopModule:
    """Requests a summary once an unfinished step reaches the request hard limit.

    The threshold is the current model's unified-budget hard input limit, read
    from ``AfterStepCtx.input_limit_tokens``. Below it the next request is still
    sendable and crossing the compaction trigger is handled by request
    compaction; at or above it continuing to call tools cannot be sent as-is,
    so the loop wraps up. Without a model budget the module never stops.
    """

    slot = "context_pressure.stop"
    requires = ("after_step.copy_input", _CTX_SLOT)
    produces = (
        _EARLY_STOP_REASON_SLOT,
        f"{_TELEMETRY_PREFIX}context_pressure_tokens",
        f"{_TELEMETRY_PREFIX}context_pressure_threshold",
    )

    async def run[FrameT: LifecycleFrame](self, frame: FrameT) -> FrameT:
        slots = frame.slots
        ctx = slots.get(_CTX_SLOT)
        if not isinstance(ctx, AfterStepCtx) or not ctx.has_more:
            return frame
        limit = ctx.input_limit_tokens
        tokens = ctx.context_tokens_estimate
        if limit is None or tokens < limit:
            return frame
        slots[_EARLY_STOP_REASON_SLOT] = "context_pressure"
        slots[f"{_TELEMETRY_PREFIX}context_pressure_tokens"] = tokens
        slots[f"{_TELEMETRY_PREFIX}context_pressure_threshold"] = limit
        return frame


async def setup(ctx: "PluginRuntimeContext") -> None:
    """装配 context_pressure：贡献 after_step 阶段的收尾请求模块。"""
    ctx.lifecycle.contribute("after_step", [ContextPressureStopModule()])
