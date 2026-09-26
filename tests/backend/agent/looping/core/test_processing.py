"""Host turn cancellation notifies transport stream owners before returning."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from agent.looping.core import AgentLoop
from bus.event_bus import EventBus
from bus.events import InboundMessage
from bus.events_lifecycle import TurnCancelled


@pytest.mark.asyncio
async def test_cancelled_processing_emits_origin_identity_for_stream_cleanup():
    loop = object.__new__(AgentLoop)
    loop._event_bus = EventBus()
    loop._processing_state = None
    loop._interrupt_states = {}
    loop._core_runner = SimpleNamespace(
        process=AsyncMock(side_effect=asyncio.CancelledError())
    )
    observed: list[TurnCancelled] = []

    async def observe(event: TurnCancelled):
        observed.append(event)

    loop._event_bus.on(TurnCancelled, observe)
    message = InboundMessage(
        "qqbot",
        "user",
        "c2c:user",
        "hello",
        metadata={"external_message_id": "source-1"},
    )
    with pytest.raises(asyncio.CancelledError):
        await loop._process(message, "role:mira")
    assert observed == [TurnCancelled("role:mira", "qqbot", "c2c:user", "source-1")]
