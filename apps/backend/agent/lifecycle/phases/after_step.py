from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TypeAlias, cast

from agent.core.turn_events import TurnEvents, read_only
from agent.lifecycle.phase import PhaseFrame, PhaseModule, topo_sort_modules
from agent.lifecycle.types import AfterStepCtx
from shiori_sdk.core.conversation import StepFinished


@dataclass
class AfterStepFrame(PhaseFrame[AfterStepCtx, AfterStepCtx]):
    pass


AfterStepModules: TypeAlias = list[PhaseModule[AfterStepFrame]]


_CTX_SLOT = "step:ctx"


class _CopyInputToCtxModule:
    slot = "after_step.copy_input"
    requires: tuple[str, ...] = ()
    produces = (_CTX_SLOT,)

    async def run(self, frame: AfterStepFrame) -> AfterStepFrame:
        frame.slots[_CTX_SLOT] = frame.input
        return frame


class _EmitStepFinishedModule:
    slot = "after_step.emit"
    requires = ("after_step.copy_input", _CTX_SLOT)
    produces = (_CTX_SLOT,)

    def __init__(self, events: TurnEvents) -> None:
        self._events = events

    async def run(self, frame: AfterStepFrame) -> AfterStepFrame:
        ctx = cast(AfterStepCtx, frame.slots[_CTX_SLOT])

        def apply(event: StepFinished) -> None:
            frame.slots[_CTX_SLOT] = replace(
                ctx,
                early_stop=event.early_stop,
                early_stop_reason=event.early_stop_reason,
                extra_metadata=dict(event.extra_metadata),
            )

        # Handlers may request the stop (context_pressure); core listeners then
        # see the final event (progress reporting).
        await self._events.emit(_step_finished(ctx), apply)
        return frame


def _step_finished(ctx: AfterStepCtx) -> StepFinished:
    """The ``StepFinished`` projection of the step's context."""
    return StepFinished(
        session_key=ctx.session_key,
        channel=ctx.channel,
        chat_id=ctx.chat_id,
        iteration=ctx.iteration,
        context_tokens_estimate=ctx.context_tokens_estimate,
        input_limit_tokens=ctx.input_limit_tokens,
        tools_called=ctx.tools_called,
        partial_reply=ctx.partial_reply,
        partial_thinking=ctx.partial_thinking,
        tools_used_so_far=ctx.tools_used_so_far,
        tool_chain_partial=tuple(read_only(group) for group in ctx.tool_chain_partial),
        has_more=ctx.has_more,
        early_stop=ctx.early_stop,
        early_stop_reason=ctx.early_stop_reason,
        extra_metadata=read_only(ctx.extra_metadata),
    )


class _ReturnAfterStepCtxModule:
    slot = "after_step.return"
    requires = ("after_step.emit", _CTX_SLOT)

    async def run(self, frame: AfterStepFrame) -> AfterStepFrame:
        frame.output = cast(AfterStepCtx, frame.slots[_CTX_SLOT])
        return frame


def default_after_step_modules(events: TurnEvents) -> AfterStepModules:
    builtins: AfterStepModules = [
        _CopyInputToCtxModule(),
        _EmitStepFinishedModule(events),
        _ReturnAfterStepCtxModule(),
    ]
    return cast(AfterStepModules, topo_sort_modules(builtins))
