"""Turn events: a plugin veto stops the stage and reaches no core listener."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from agent.core.turn_events import TurnEvents
from bus.event_bus import EventBus
from shiori_sdk.core.conversation import ReasoningStarting
from shiori_sdk.kernel import Context, Kernel, PluginSpec, Veto


async def _vetoing_kernel() -> Kernel:
    async def refuse(event: ReasoningStarting) -> Veto:
        return Veto("先别想了")

    async def setup(ctx: Context) -> None:
        ctx.on(ReasoningStarting, refuse)

    kernel = Kernel()
    await kernel.start([PluginSpec("refuser", setup)])
    return kernel


def _starting() -> ReasoningStarting:
    return ReasoningStarting(
        session_key="role:mira",
        channel="desktop",
        chat_id="mira",
        content="hello",
        timestamp=datetime.now(timezone.utc),
    )


async def test_a_veto_reaches_the_stage_and_fans_nothing_out() -> None:
    kernel = await _vetoing_kernel()
    bus = EventBus()
    heard: list[object] = []
    bus.on(ReasoningStarting, heard.append)
    applied: list[ReasoningStarting] = []
    vetoes: list[Veto] = []

    await TurnEvents(bus, lambda: kernel).emit(
        _starting(), applied.append, vetoes.append
    )

    assert vetoes == [Veto("先别想了")]
    assert applied == [] and heard == []


async def test_a_veto_fails_a_stage_that_cannot_stop() -> None:
    kernel = await _vetoing_kernel()

    with pytest.raises(RuntimeError, match="先别想了"):
        await TurnEvents(EventBus(), lambda: kernel).emit(_starting(), lambda _: None)
