from __future__ import annotations

from dataclasses import replace

from agent.core.turn_events import TurnEvents, read_only
from agent.lifecycle.types import AfterStepCtx
from shiori_sdk.core.conversation import StepFinished


class AfterStepPhase:
    """Closes one reasoning step through ``StepFinished``."""

    def __init__(self, events: TurnEvents) -> None:
        self._events = events

    async def run(self, ctx: AfterStepCtx) -> AfterStepCtx:
        """Emits ``StepFinished`` and returns ``ctx`` with its writable fields.

        Handlers may request the stop (context_pressure); core listeners then
        see the final event (progress reporting).
        """
        result = ctx

        def apply(event: StepFinished) -> None:
            nonlocal result
            result = replace(
                ctx,
                early_stop=event.early_stop,
                early_stop_reason=event.early_stop_reason,
                extra_metadata=dict(event.extra_metadata),
            )

        await self._events.emit(_step_finished(ctx), apply)
        return result


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
