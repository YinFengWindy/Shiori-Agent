"""The host stream sink: gated by the published channel, carrying the source identity."""

from unittest.mock import Mock

import pytest

from agent.looping.core import AgentLoop
from bus.event_bus import EventBus
from core.common.channel_directory import ChannelDirectory
from shiori_sdk.messages import InboundMessage
from shiori_sdk.channel_events import StreamDeltaReady, TurnStarted


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


class _LiveChannel:
    """A neutral channel that opts one chat into live previews and records events."""

    name = "live_demo"

    def __init__(self, event_bus: EventBus) -> None:
        self.events: list[TurnStarted | StreamDeltaReady] = []
        event_bus.on(TurnStarted, self._record)
        event_bus.on(StreamDeltaReady, self._record)

    def supports_stream_events(self, chat_id: str) -> bool:
        return chat_id == "private"

    async def _record(self, event: TurnStarted | StreamDeltaReady) -> None:
        self.events.append(event)


@pytest.mark.asyncio
async def test_published_channel_decides_streaming_and_receives_turn_events():
    events = EventBus()
    channel = _LiveChannel(events)
    directory = ChannelDirectory()
    directory.bind({channel.name: channel}.get)
    loop = object.__new__(AgentLoop)
    loop._event_bus = events
    loop._active_turn_states = {}
    loop._channel_directory = directory
    private = InboundMessage(
        channel.name,
        "user",
        "private",
        "hello",
        metadata={"external_message_id": "in-1", "session_key_override": "role:a"},
    )
    group = InboundMessage(channel.name, "user", "group", "hello")

    # Only chats the published channel opts in get a stream sink.
    assert loop._build_stream_event_sink(group) is None
    await loop._observe_turn_started(private, "role:a")
    sink = loop._build_stream_event_sink(private)
    assert sink is not None
    await sink("pre")
    await sink({"content_delta": "view", "thinking_delta": "hmm"})

    started, *deltas = channel.events
    assert isinstance(started, TurnStarted)
    assert (started.session_key, started.chat_id, started.external_message_id) == (
        "role:a",
        "private",
        "in-1",
    )
    assert [
        (
            event.session_key,
            event.channel,
            event.chat_id,
            event.content_delta,
            event.thinking_delta,
            event.external_message_id,
        )
        for event in deltas
        if isinstance(event, StreamDeltaReady)
    ] == [
        ("role:a", channel.name, "private", "pre", "", "in-1"),
        ("role:a", channel.name, "private", "view", "hmm", "in-1"),
    ]
    await events.aclose()
