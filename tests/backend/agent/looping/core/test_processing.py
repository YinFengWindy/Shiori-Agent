"""Host turn cancellation notifies transport stream owners before returning."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from agent.looping.core import AgentLoop
from bus.event_bus import EventBus
from bus.events import InboundMessage, OutboundMessage
from bus.events_lifecycle import TurnCancelled
from core.common.message_source import MessageSource


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


@pytest.mark.asyncio
async def test_direct_desktop_turn_uses_persisted_sender_identity():
    loop = object.__new__(AgentLoop)
    loop._active_tasks = {}
    loop._active_turn_states = {}
    loop._session_services = SimpleNamespace(
        session_manager=SimpleNamespace(
            role_session_key=lambda role_id: f"role:{role_id}"
        )
    )
    loop._process = AsyncMock(
        return_value=OutboundMessage(
            channel="desktop", chat_id="role:mira", content="ok"
        )
    )
    metadata = {
        "source": "desktop",
        "role_id": "mira",
        "sender_id": "desktop",
        "chat_type": "desktop",
        "transport_channel": "desktop",
        "transport_chat_id": "role:mira",
    }

    await AgentLoop.process_direct(
        loop,
        content="刚才群里是谁说的？",
        session_key="role:mira",
        channel="desktop",
        chat_id="role:mira",
        metadata=metadata,
    )

    current = loop._process.await_args.args[0]
    assert current.sender == "desktop"
    assert MessageSource.from_inbound(current) == MessageSource.from_metadata(
        current.metadata, session_key="role:mira"
    )
