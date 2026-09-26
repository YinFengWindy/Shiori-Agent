"""The host stream sink retains the originating transport message identity."""

from unittest.mock import Mock

import pytest

from agent.looping.core import AgentLoop
from bus.event_bus import EventBus
from bus.events import InboundMessage
from bus.events_lifecycle import StreamDeltaReady


@pytest.mark.asyncio
@pytest.mark.parametrize("source_id", ["source-1", ""])
async def test_stream_sink_captures_original_external_message_id(source_id):
    loop = object.__new__(AgentLoop)
    loop._event_bus = EventBus()
    loop._active_turn_states = {}
    loop._channel_directory = Mock()
    loop._channel_directory.supports_stream_events.return_value = True
    observed: list[StreamDeltaReady] = []

    async def observe(event: StreamDeltaReady):
        observed.append(event)

    loop._event_bus.on(StreamDeltaReady, observe)
    message = InboundMessage(
        "qqbot",
        "user",
        "c2c:user",
        "hello",
        metadata={"external_message_id": source_id},
    )
    sink = loop._build_stream_event_sink(message)
    assert sink is not None
    message.metadata["external_message_id"] = "changed-after-sink-creation"
    await sink("first")
    await sink("second")
    assert [event.external_message_id for event in observed] == [source_id, source_id]
