from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from agent.looping.interrupt import TurnInterruptState
from bus.event_bus import EventBus
from desktop_bridge.chat_service import DesktopChatService
from session.manager import SessionManager
from session.manager.models import INTERRUPTED_TURN_METADATA_KEY


@pytest.mark.asyncio
async def test_desktop_chat_service_emits_chat_error_event(tmp_path):
    session_manager = SessionManager(tmp_path)
    event_bus = EventBus()
    emitted: list[dict] = []

    class _Loop:
        async def process_direct(self, *args, **kwargs):
            raise RuntimeError("boom")

    async def _emit_payload(emit_event, payload: dict):
        result = emit_event(payload)
        if result is not None:
            await result

    async def _emit_session_updated(
        request_id: str,
        session,
        emit_event,
    ) -> None:
        raise AssertionError("error path should not emit session.updated")

    service = DesktopChatService(
        agent_loop=_Loop(),  # type: ignore[arg-type]
        event_bus=event_bus,
        session_manager=session_manager,
        role_id_from_session_key=lambda key: "mira",
        sync_desktop_session_thread=lambda session, role_id: None,
        emit_payload=_emit_payload,
        emit_session_updated=_emit_session_updated,
    )

    with pytest.raises(RuntimeError, match="boom"):
        await service.run_chat_turn(
            request_id="1",
            session_key="role:mira",
            content="hi",
            media=[],
            metadata=None,
            omit_user_turn=True,
            emit_event=emitted.append,
        )

    assert emitted == [
        {
            "id": "1",
            "type": "event",
            "method": "chat.error",
                "payload": {
                    "session_key": "role:mira",
                    "turn_id": "1",
                    "message": "boom",
                },
        }
    ]


@pytest.mark.asyncio
async def test_cancelled_reply_survives_session_manager_reload(tmp_path):
    session_manager = SessionManager(tmp_path)
    session_key = "role:mira"
    _ = session_manager.get_or_create(session_key)
    started = asyncio.Event()
    state = TurnInterruptState(
        session_key=session_key,
        original_user_message="hello",
        partial_reply="partial answer",
        partial_thinking="retain this reasoning",
        tools_used=["web_search"],
        tool_chain_partial=[{"text": "", "calls": [{"name": "web_search"}]}],
    )

    async def _process_direct(*_args, **_kwargs):
        started.set()
        await asyncio.Event().wait()

    service = DesktopChatService(
        agent_loop=SimpleNamespace(
            process_direct=_process_direct,
            request_interrupt=Mock(
                return_value=SimpleNamespace(
                    status="interrupted",
                    message="cancelled",
                    state=state,
                )
            ),
            discard_interrupt_state=Mock(),
        ),
        event_bus=EventBus(),
        session_manager=session_manager,
        role_id_from_session_key=lambda _key: "mira",
        sync_desktop_session_thread=lambda _session, *, role_id: None,
        emit_payload=lambda _emit, _payload: asyncio.sleep(0),
        emit_session_updated=lambda **_kwargs: asyncio.sleep(0),
    )
    service.start_chat_turn(
        request_id="request-1",
        turn_id="turn-1",
        session_key=session_key,
        content="hello",
        media=[],
        metadata={},
        omit_user_turn=True,
        emit_event=lambda _payload: None,
    )
    await started.wait()

    result = await service.cancel_chat_turn_async(session_key, "turn-1")

    assert result.status == "interrupted"
    reloaded = SessionManager(tmp_path).get_or_create(session_key)
    assert reloaded.metadata[INTERRUPTED_TURN_METADATA_KEY]["turn_id"] == "turn-1"
    assistant = reloaded.messages[-1]
    assert assistant["content"] == "partial answer"
    assert assistant["reasoning_content"] == "retain this reasoning"
    assert assistant["tool_chain"] == state.tool_chain_partial
    assert assistant["metadata"]["interrupted_reply"] is True

    await service.aclose()
