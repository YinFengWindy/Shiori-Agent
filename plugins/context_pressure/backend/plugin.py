from __future__ import annotations

from shiori_sdk import PluginRuntimeContext
from shiori_sdk.lifecycle import AfterStepCtx, LifecycleFrame

_CTX_SLOT = "step:ctx"
_EARLY_STOP_REASON_SLOT = "step:early_stop_reason"
_TELEMETRY_PREFIX = "step:telemetry:"

_MODEL_CONTEXT_WINDOW_TOKENS = 1_000_000
_CONTEXT_PRESSURE_STOP_THRESHOLD_TOKENS = _MODEL_CONTEXT_WINDOW_TOKENS * 80 // 100


class ContextPressureStopModule:
    """Requests a summary when an unfinished step crosses the plugin budget."""

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
        tokens = ctx.context_tokens_estimate
        if tokens <= _CONTEXT_PRESSURE_STOP_THRESHOLD_TOKENS:
            return frame
        slots[_EARLY_STOP_REASON_SLOT] = "context_pressure"
        slots[f"{_TELEMETRY_PREFIX}context_pressure_tokens"] = tokens
        slots[f"{_TELEMETRY_PREFIX}context_pressure_threshold"] = (
            _CONTEXT_PRESSURE_STOP_THRESHOLD_TOKENS
        )
        return frame


async def setup(ctx: "PluginRuntimeContext") -> None:
    """装配 context_pressure：贡献 after_step 阶段的收尾请求模块。"""
    ctx.lifecycle.contribute("after_step", [ContextPressureStopModule()])
