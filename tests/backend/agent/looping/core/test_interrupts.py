"""Turn start events retain transport identity without requiring it."""

import pytest
import asyncio
from unittest.mock import AsyncMock

from agent.looping.core import AgentLoop
from bus.event_bus import EventBus
from shiori_sdk.messages import InboundMessage
from shiori_sdk.channel_events import TurnStarted
from agent.looping.interrupt import turn_tracking_key


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


async def test_two_chats_keep_progress_and_explicit_stop_separate():
    loop = object.__new__(AgentLoop)
    loop._active_turn_states = {}
    loop._active_tasks = {}
    loop._interrupt_states = {}
    loop._compact_command = AsyncMock(return_value=None)
    entered = {chat: asyncio.Event() for chat in ("a", "b")}
    release = asyncio.Event()

    async def process(item, key):
        loop._append_partial_thinking(key, item.chat_id)
        entered[item.chat_id].set()
        await release.wait()

    loop._process_role_scoped = process
    tasks = [
        asyncio.create_task(
            loop.process_inbound(
                InboundMessage(
                    "qqbot",
                    "user",
                    chat,
                    chat,
                    metadata={"session_key_override": "role:mira"},
                )
            )
        )
        for chat in ("a", "b")
    ]
    await asyncio.gather(*(event.wait() for event in entered.values()))
    assert loop.request_interrupt("role:mira").status == "idle"
    stopped = loop.request_interrupt("role:mira", channel="qqbot", chat_id="a")
    assert stopped.state.partial_thinking == "a"
    await tasks[0]
    assert not tasks[1].done()
    assert (
        loop._active_turn_states[
            turn_tracking_key("role:mira", "qqbot", "b")
        ].partial_thinking
        == "b"
    )
    release.set()
    await tasks[1]
    assert loop._active_turn_states == {}
