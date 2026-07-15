from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from bus.event_bus import EventBus
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
