from __future__ import annotations

from types import SimpleNamespace

import pytest

from bus.event_bus import EventBus
from bus.events_lifecycle import TurnCommitted
from core.roles import RoleStore
from desktop_bridge.service import DesktopBridgeService
from session.manager import SessionManager


@pytest.mark.asyncio
async def test_external_turn_committed_broadcasts_role_session_once(tmp_path) -> None:
    role_store = RoleStore(tmp_path)
    role_store.create_role(
        role_id="mira",
        name="Mira",
        system_prompt="You are Mira.",
    )
    session_manager = SessionManager(tmp_path)
    event_bus = EventBus()
    service = DesktopBridgeService(
        workspace=tmp_path,
        role_store=role_store,
        session_manager=session_manager,
        agent_loop=SimpleNamespace(),
        event_bus=event_bus,
    )
    emitted: list[dict] = []
    service.add_event_listener(emitted.append)

    session = session_manager.get_or_create("role:mira")
    session.add_message(
        "assistant",
        "来自 Telegram",
        metadata={
            "role_id": "mira",
            "thread_id": "thread:mira:telegram:123",
            "transport_channel": "telegram",
            "transport_chat_id": "123",
        },
    )
    session_manager.save(session)

    await event_bus.fanout(
        TurnCommitted(
            session_key="role:mira",
            channel="telegram",
            chat_id="123",
            input_message="hello",
            persisted_user_message="hello",
            assistant_response="来自 Telegram",
            tools_used=[],
            role_id="mira",
            request_id="telegram-message-1",
            thread_id="thread:mira:telegram:123",
        )
    )
    assert len(emitted) == 1
    assert emitted[0]["method"] == "session.updated"
    assert emitted[0]["payload"]["session"]["key"] == "role:mira"

    await event_bus.fanout(
        TurnCommitted(
            session_key="role:mira",
            channel="desktop",
            chat_id="role:mira",
            input_message="hello",
            persisted_user_message="hello",
            assistant_response="来自桌面",
            tools_used=[],
            role_id="mira",
            request_id="desktop-message-1",
            thread_id="thread:mira:desktop",
        )
    )
    assert len(emitted) == 1
