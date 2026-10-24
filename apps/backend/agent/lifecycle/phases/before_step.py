from __future__ import annotations

from dataclasses import dataclass
from typing import TypeAlias, cast

from agent.core.passive_support import (
    build_context_hint_message,
    estimate_messages_tokens,
)
from agent.lifecycle.phase import PhaseFrame, PhaseModule, topo_sort_modules
from agent.core.turn_events import TurnEvents
from agent.lifecycle.types import BeforeStepCtx, BeforeStepInput
from shiori_sdk.core.conversation import StepStarting
from shiori_sdk.kernel import Veto


@dataclass
class BeforeStepFrame(PhaseFrame[BeforeStepInput, BeforeStepCtx]):
    pass


BeforeStepModules: TypeAlias = list[PhaseModule[BeforeStepFrame]]


_CTX_SLOT = "step:ctx"


class _BuildBeforeStepCtxModule:
    slot = "before_step.build_ctx"
    requires: tuple[str, ...] = ()
    produces = (_CTX_SLOT,)

    async def run(self, frame: BeforeStepFrame) -> BeforeStepFrame:
        input = frame.input
        frame.slots[_CTX_SLOT] = BeforeStepCtx(
            session_key=input.session_key,
            channel=input.channel,
            chat_id=input.chat_id,
            iteration=input.iteration,
            input_tokens_estimate=estimate_messages_tokens(input.messages),
            visible_tool_names=(
                frozenset(input.visible_names)
                if input.visible_names is not None
                else None
            ),
        )
        return frame


class _EmitBeforeStepCtxModule:
    slot = "before_step.emit"
    requires = ("before_step.build_ctx", _CTX_SLOT)
    produces = (_CTX_SLOT,)

    def __init__(self, events: TurnEvents) -> None:
        self._events = events

    async def run(self, frame: BeforeStepFrame) -> BeforeStepFrame:
        ctx = cast(BeforeStepCtx, frame.slots[_CTX_SLOT])

        def apply(event: StepStarting) -> None:
            ctx.extra_hints[:] = event.extra_hints

        def vetoed(veto: Veto) -> None:
            ctx.early_stop, ctx.early_stop_reply = True, veto.reason

        await self._events.emit(_step_starting(ctx), apply, vetoed)
        return frame


def _step_starting(ctx: BeforeStepCtx) -> StepStarting:
    """The ``StepStarting`` projection of the step's context."""
    return StepStarting(
        session_key=ctx.session_key,
        channel=ctx.channel,
        chat_id=ctx.chat_id,
        iteration=ctx.iteration,
        input_tokens_estimate=ctx.input_tokens_estimate,
        visible_tool_names=ctx.visible_tool_names,
        extra_hints=tuple(ctx.extra_hints),
    )


class _InjectHintsModule:
    slot = "before_step.inject_hints"
    requires = ("before_step.emit", _CTX_SLOT)

    async def run(self, frame: BeforeStepFrame) -> BeforeStepFrame:
        ctx = cast(BeforeStepCtx, frame.slots[_CTX_SLOT])
        if ctx.extra_hints:
            frame.input.messages.append(
                build_context_hint_message(
                    "plugin_hints",
                    "\n".join(ctx.extra_hints),
                )
            )
        return frame


class _ReturnBeforeStepCtxModule:
    slot = "before_step.return"
    requires = ("before_step.inject_hints", _CTX_SLOT)

    async def run(self, frame: BeforeStepFrame) -> BeforeStepFrame:
        frame.output = cast(BeforeStepCtx, frame.slots[_CTX_SLOT])
        return frame


def default_before_step_modules(events: TurnEvents) -> BeforeStepModules:
    builtins: BeforeStepModules = [
        _BuildBeforeStepCtxModule(),
        _EmitBeforeStepCtxModule(events),
        _InjectHintsModule(),
        _ReturnBeforeStepCtxModule(),
    ]
    return cast(BeforeStepModules, topo_sort_modules(builtins))
