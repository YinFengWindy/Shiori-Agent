from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from bus.event_bus import EventBus
from bus.events_lifecycle import StreamDeltaReady
from desktop_bridge.chat_service import ChatTurnBusyError, DesktopChatService


@pytest.mark.asyncio
async def test_chat_service_allows_only_one_turn_per_session() -> None:
    started = asyncio.Event()

    async def _process_direct(*_args, **_kwargs) -> None:
        started.set()
        await asyncio.Event().wait()

    service = DesktopChatService(
        agent_loop=SimpleNamespace(process_direct=_process_direct),
        event_bus=EventBus(),
        session_manager=SimpleNamespace(get_or_create=Mock()),
        role_id_from_session_key=Mock(return_value="role-1"),
        sync_desktop_session_thread=Mock(),
        emit_payload=AsyncMock(),
        emit_session_updated=AsyncMock(),
    )
    arguments = {
        "request_id": "request-1",
        "session_key": "role:role-1",
        "content": "hello",
        "media": [],
        "metadata": {},
        "omit_user_turn": True,
        "emit_event": AsyncMock(),
    }
    service.start_chat_turn(**arguments)
    await started.wait()

    with pytest.raises(ChatTurnBusyError):
        service.start_chat_turn(**{**arguments, "request_id": "request-2"})

    await service.aclose()
    assert service.is_busy("role:role-1") is False


@pytest.mark.asyncio
async def test_chat_service_close_awaits_task_listener_cleanup() -> None:
    event_bus = EventBus()
    started = asyncio.Event()

    async def _process_direct(*_args, **_kwargs) -> None:
        started.set()
        await asyncio.Event().wait()

    service = DesktopChatService(
        agent_loop=SimpleNamespace(process_direct=_process_direct),
        event_bus=event_bus,
        session_manager=SimpleNamespace(get_or_create=Mock()),
        role_id_from_session_key=Mock(return_value="role-1"),
        sync_desktop_session_thread=Mock(),
        emit_payload=AsyncMock(),
        emit_session_updated=AsyncMock(),
    )
    service.start_chat_turn(
        request_id="request-1",
        session_key="role:role-1",
        content="hello",
        media=[],
        metadata={},
        omit_user_turn=True,
        emit_event=AsyncMock(),
    )
    await started.wait()

    await service.aclose()

    assert event_bus._handlers == {}


@pytest.mark.asyncio
async def test_cancel_voice_turn_interrupts_owned_chat_and_rejects_late_tts_delta() -> None:
    event_bus = EventBus()
    started = asyncio.Event()
    release = asyncio.Event()
    interrupt = Mock()
    tts_service = SimpleNamespace(
        tts_enabled=True,
        tts_provider="minimax",
        stream_synthesize_result=Mock(),
    )

    async def _process_direct(*_args, **_kwargs) -> None:
        started.set()
        await release.wait()

    service = DesktopChatService(
        agent_loop=SimpleNamespace(
            process_direct=_process_direct,
            request_interrupt=interrupt,
        ),
        event_bus=event_bus,
        session_manager=SimpleNamespace(
            get_or_create=Mock(
                return_value=SimpleNamespace(
                    metadata={"role_runtime_config": {"tts": {"voice_id": "mira"}}}
                )
            )
        ),
        role_id_from_session_key=Mock(return_value="role-1"),
        sync_desktop_session_thread=Mock(),
        emit_payload=AsyncMock(),
        emit_session_updated=AsyncMock(),
        tts_service=tts_service,
    )
    service.start_chat_turn(
        request_id="request-voice-1",
        session_key="role:role-1",
        content="hello",
        media=[],
        metadata={"input_method": "voice", "voice_turn_id": "voice-turn-1"},
        omit_user_turn=True,
        emit_event=AsyncMock(),
    )
    await started.wait()

    assert service.cancel_voice_turn("voice-turn-1") is True
    interrupt.assert_called_once_with(
        "role:role-1",
        sender="desktop",
        command="/cancel",
    )
    await event_bus.observe(
        StreamDeltaReady(
            session_key="role:role-1",
            channel="desktop",
            chat_id="role:role-1",
            content_delta="晚到的旧回复。",
        )
    )
    assert tts_service.stream_synthesize_result.call_count == 0

    release.set()
    await service.aclose()
