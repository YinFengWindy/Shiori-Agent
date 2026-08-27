from __future__ import annotations

import pytest

from bus.event_bus import EventBus
from desktop_bridge.chat_service import DesktopChatService
from session.manager import SessionManager


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
                "message": "boom",
            },
        }
    ]
