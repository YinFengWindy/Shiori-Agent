from __future__ import annotations

from agent.core.passive_support import (
    build_context_hint_message,
    estimate_messages_tokens,
)
from agent.core.turn_events import TurnEvents
from agent.lifecycle.types import BeforeStepCtx, BeforeStepInput
from shiori_sdk.core.conversation import StepStarting
from shiori_sdk.kernel import Veto


class BeforeStepPhase:
    """Readies one reasoning step: ``StepStarting``, then its hints in the request."""

    def __init__(self, events: TurnEvents) -> None:
        self._events = events

    async def run(self, input: BeforeStepInput) -> BeforeStepCtx:
        """Emits ``StepStarting`` and appends its hints to ``input.messages``."""
        ctx = BeforeStepCtx(
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

        def apply(event: StepStarting) -> None:
            ctx.extra_hints[:] = event.extra_hints

        def vetoed(veto: Veto) -> None:
            ctx.early_stop, ctx.early_stop_reply = True, veto.reason

        await self._events.emit(_step_starting(ctx), apply, vetoed)
        if ctx.extra_hints:
            input.messages.append(
                build_context_hint_message(
                    "plugin_hints",
                    "\n".join(ctx.extra_hints),
                )
            )
        return ctx


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
