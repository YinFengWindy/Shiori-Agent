from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from agent.tools.message_push import MessagePushTool
from bus.event_bus import EventBus
from bus.events_lifecycle import ProactiveMessageCommitted, TurnCommitted
from conversation.push_sync import ExternalImageSyncService
from core.roles import RoleStore
from desktop_bridge.service import DesktopBridgeService
from session.manager import SessionManager


@pytest.mark.asyncio
async def test_novelai_regenerate_message_media_returns_updated_session(
    tmp_path,
) -> None:
    role_store = RoleStore(tmp_path)
    role_store.create_role(
        role_id="mira",
        name="Mira",
        system_prompt="You are Mira.",
    )
    session_manager = SessionManager(tmp_path)
    session = session_manager.get_or_create("role:mira")
    session.add_message("assistant", "scene", media=[str(tmp_path / "new.png")])
    session_manager.save(session)
    service = DesktopBridgeService(
        workspace=tmp_path,
        role_store=role_store,
        session_manager=session_manager,
        agent_loop=SimpleNamespace(),
        event_bus=EventBus(),
    )
    service.image_service.regenerate_message_media = AsyncMock(
        return_value=({"record_id": "new-record"}, session)
    )
    emitted = Mock()

    response = await service.handle(
        {
            "id": "regenerate-1",
            "method": "novelai.regenerateMessageMedia",
            "payload": {
                "session_key": "role:mira",
                "message_id": session.messages[-1]["id"],
                "media_index": 0,
            },
        },
        emit_event=emitted,
    )

    assert response.error is None
    assert response.payload["result"]["record_id"] == "new-record"
    assert response.payload["session"]["messages"][-1]["media"] == [
        str(tmp_path / "new.png")
    ]
    assert emitted.call_args.args[0]["method"] == "session.updated"


@pytest.mark.asyncio
async def test_observation_bridge_routes_only_through_the_owned_service(tmp_path) -> None:
    role_store = RoleStore(tmp_path)
    session_manager = SessionManager(tmp_path)
    observation = SimpleNamespace(
        analyze=AsyncMock(return_value={"frame_id": "frame-1"}),
        remember=AsyncMock(return_value={"item_id": "event-1"}),
    )
    service = DesktopBridgeService(
        workspace=tmp_path,
        role_store=role_store,
        session_manager=session_manager,
        agent_loop=SimpleNamespace(),
        event_bus=EventBus(),
        observation_service=observation,
    )

    analyzed = await service.handle(
        {"id": "observe-1", "method": "observation.analyze", "payload": {"frame_id": "frame-1"}},
        emit_event=Mock(),
    )
    remembered = await service.handle(
        {"id": "observe-2", "method": "observation.remember", "payload": {"summary": "共同经历"}},
        emit_event=Mock(),
    )

    assert analyzed.error is None
    assert analyzed.payload == {"frame_id": "frame-1"}
    assert remembered.error is None
    assert remembered.payload == {"item_id": "event-1"}
    observation.analyze.assert_awaited_once()
    observation.remember.assert_awaited_once()


@pytest.mark.asyncio
async def test_chat_send_returns_busy_before_persisting_second_message(tmp_path) -> None:
    role_store = RoleStore(tmp_path)
    role_store.create_role(
        role_id="mira",
        name="Mira",
        system_prompt="You are Mira.",
    )
    session_manager = SessionManager(tmp_path)
    service = DesktopBridgeService(
        workspace=tmp_path,
        role_store=role_store,
        session_manager=session_manager,
        agent_loop=SimpleNamespace(),
        event_bus=EventBus(),
    )
    service.chat_service.is_busy = Mock(return_value=True)

    response = await service.handle(
        {
            "id": "request-2",
            "method": "chat.send",
            "payload": {"role_id": "mira", "content": "second"},
        },
        emit_event=Mock(),
    )

    assert response.error is not None
    assert response.error.code == "chat_busy"
    session = session_manager.get_or_create("role:mira")
    assert session.messages == []


@pytest.mark.asyncio
async def test_pet_observation_starts_a_role_turn_without_persisting_a_fake_user_message(
    tmp_path,
) -> None:
    role_store = RoleStore(tmp_path)
    role_store.create_role(role_id="mira", name="Mira", system_prompt="test")
    session_manager = SessionManager(tmp_path)
    service = DesktopBridgeService(
        workspace=tmp_path,
        role_store=role_store,
        session_manager=session_manager,
        agent_loop=SimpleNamespace(),
        event_bus=EventBus(),
    )
    service.chat_service.start_chat_turn = Mock()

    response = await service.handle(
        {
            "id": "observe-screen-1",
            "method": "chat.observeScreen",
            "payload": {"role_id": "mira"},
        },
        emit_event=Mock(),
    )

    assert response.error is None
    assert session_manager.get_or_create("role:mira").messages == []
    assert service.chat_service.start_chat_turn.call_args.kwargs["omit_user_turn"] is True
    assert "observe_screen" in service.chat_service.start_chat_turn.call_args.kwargs["content"]


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

    await event_bus.fanout(
        ProactiveMessageCommitted(
            session_key="role:other",
            channel="telegram",
            role_id="mira",
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


@pytest.mark.asyncio
async def test_external_proactive_media_commit_broadcasts_role_session(tmp_path) -> None:
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
        "给你看张图",
        media=["D:\\media\\scene.png"],
        proactive=True,
        metadata={
            "role_id": "mira",
            "thread_id": "thread:mira:telegram:123",
            "transport_channel": "telegram",
            "transport_chat_id": "123",
        },
    )
    session_manager.save(session)

    await event_bus.fanout(
        ProactiveMessageCommitted(
            session_key="role:mira",
            channel="telegram",
            role_id="mira",
        )
    )

    assert len(emitted) == 1
    assert emitted[0]["method"] == "session.updated"
    assert emitted[0]["payload"]["session"]["messages"][-1]["media"] == [
        "D:\\media\\scene.png"
    ]

    await event_bus.fanout(
        ProactiveMessageCommitted(
            session_key="role:mira",
            channel="desktop",
            role_id="mira",
        )
    )
    assert len(emitted) == 1


@pytest.mark.asyncio
async def test_external_image_push_persists_and_broadcasts_desktop_session(
    tmp_path,
) -> None:
    role_store = RoleStore(tmp_path)
    role_store.create_role(
        role_id="mira",
        name="Mira",
        system_prompt="You are Mira.",
    )
    session_manager = SessionManager(tmp_path)
    session_manager.open_role_session("mira", role_name="Mira")
    event_bus = EventBus()
    _ = ExternalImageSyncService(
        session_manager=session_manager,
        event_bus=event_bus,
    )
    service = DesktopBridgeService(
        workspace=tmp_path,
        role_store=role_store,
        session_manager=session_manager,
        agent_loop=SimpleNamespace(),
        event_bus=event_bus,
    )
    emitted: list[dict] = []
    service.add_event_listener(emitted.append)
    push_tool = MessagePushTool(event_bus=event_bus)

    async def send_image(_chat_id: str, _image: str) -> None:
        return None

    push_tool.register_channel("telegram", image=send_image)
    image = str(tmp_path / "scene.png")

    result = await push_tool.execute(
        channel="telegram",
        chat_id="123",
        image=image,
        role_id="mira",
        session_key="role:mira",
    )

    assert result == "图片已发送"
    assert len(emitted) == 1
    assert emitted[0]["method"] == "session.updated"
    assert emitted[0]["payload"]["session"]["messages"][-1]["media"] == [image]
