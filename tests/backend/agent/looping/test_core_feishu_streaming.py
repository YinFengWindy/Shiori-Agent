"""Real AgentLoop stream gating reaches the Feishu adapter's external CardKit API."""

import asyncio

from agent.looping.core import AgentLoop
from bus.event_bus import EventBus
from shiori_sdk.messages import InboundMessage, OutboundMessage
from bus.queue import MessageBus
from core.common.channel_directory import ChannelDirectory
from plugins.feishu.tests.conftest import build_harness, message_event, CHAT_ID


async def test_agent_stream_and_bus_final_use_one_feishu_card(tmp_path):
    harness = build_harness(tmp_path)
    events = EventBus()
    bus = MessageBus()
    harness.context.event_bus = events
    harness.context.bus = bus
    directory = ChannelDirectory()
    directory.bind({"feishu": harness.channel}.get)
    loop = object.__new__(AgentLoop)
    loop._event_bus = events
    loop._active_turn_states = {}
    loop._channel_directory = directory
    try:
        connection = await harness.start()
        connection.emit(message_event())
        inbound = await asyncio.wait_for(bus.consume_inbound(), 1)
        assert isinstance(inbound, InboundMessage)
        await loop._observe_turn_started(inbound, inbound.session_key)
        sink = loop._build_stream_event_sink(inbound)
        assert sink is not None
        await sink("预览")
        # The final reply waits for an in-flight preview write by itself, so it
        # is enough that the preview reached Feishu.
        async with asyncio.timeout(1):
            while not harness.api.bodies("stream_text"):
                await asyncio.sleep(0.001)
        await bus._dispatch_message(
            OutboundMessage(
                "feishu",
                CHAT_ID,
                "完整回复",
                metadata={"session_key_override": inbound.session_key},
            )
        )
        assert len(harness.api.bodies("create_card")) == 1
        assert len(harness.api.bodies("reply")) == 1
        assert harness.api.bodies("stream_text")[-1]["content"] == "完整回复"
        assert len(harness.api.bodies("card_settings")) == 1
        assert harness.api.sent_texts() == []
        assert harness.hub.delivery_statuses() == ["sent"]
    finally:
        await harness.channel.stop()
        await events.aclose()
