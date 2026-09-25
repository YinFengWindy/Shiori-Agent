"""Turn start events retain transport identity without requiring it."""

import pytest

from agent.looping.core import AgentLoop
from bus.event_bus import EventBus
from bus.events import InboundMessage
from bus.events_lifecycle import TurnStarted


@pytest.mark.asyncio
@pytest.mark.parametrize("metadata", [{"external_message_id": "source-1"}, {}])
async def test_turn_started_carries_originating_external_message_id(metadata):
    loop = object.__new__(AgentLoop)
    loop._event_bus = EventBus()
    observed: list[TurnStarted] = []

    async def observe(event: TurnStarted):
        observed.append(event)

    loop._event_bus.on(TurnStarted, observe)
    message = InboundMessage("qqbot", "user", "c2c:user", "hello", metadata=metadata)
    await loop._observe_turn_started(message, "role:mira")
    [event] = observed
    assert event.external_message_id == metadata.get("external_message_id", "")
    assert event.session_key == "role:mira"
    assert event.timestamp == message.timestamp
