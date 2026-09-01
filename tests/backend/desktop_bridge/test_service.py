from __future__ import annotations

import asyncio
import threading
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from agent.tools.message_push import MessagePushTool
from bus.event_bus import EventBus
from bus.events_lifecycle import ProactiveMessageCommitted, RoleDeleted, TurnCommitted
from conversation.push_sync import ExternalImageSyncService
from core.roles import RoleStore
from core.roles.services import RoleAggregateService
from desktop_bridge.service import DesktopBridgeService
from desktop_bridge.voice.voice_service import (
    VoiceOperationMetrics,
    VoiceServiceError,
    VoiceTranscriptionResult,
)
from session.manager import SessionManager


@pytest.mark.asyncio
async def test_injected_role_service_publishes_role_deleted(tmp_path) -> None:
    role_store = RoleStore(tmp_path)
    session_manager = SessionManager(tmp_path)
    role_service = RoleAggregateService.from_runtime(
        workspace=tmp_path,
        role_store=role_store,
        session_manager=session_manager,
    )
    role_service.create_role(
        role_id="mira",
        name="Mira",
        system_prompt="You are Mira.",
    )
    event_bus = EventBus()
    deleted_role_ids: list[str] = []
    invalidate_role_memories = Mock(return_value=1)
    event_bus.on(RoleDeleted, lambda event: deleted_role_ids.append(event.role_id))
    service = DesktopBridgeService(
        workspace=tmp_path,
        role_store=role_store,
        session_manager=session_manager,
        agent_loop=SimpleNamespace(),
        event_bus=event_bus,
        role_service=role_service,
        memory_engine=SimpleNamespace(
            invalidate_role_memories=invalidate_role_memories,
        ),
    )

    response = await service.handle(
        {
            "id": "delete-role-1",
            "method": "roles.delete",
            "payload": {"role_id": "mira"},
        },
        emit_event=Mock(),
    )
    await event_bus.drain()

    assert response.error is None
    assert deleted_role_ids == ["mira"]
    invalidate_role_memories.assert_called_once_with("mira")
    await service.aclose()


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
    assert response.payload["message"]["media"] == [
        str(tmp_path / "new.png")
    ]
    assert emitted.call_args.args[0]["method"] == "session.updated"
    assert emitted.call_args.args[0]["payload"]["change"] == "message_updated"


@pytest.mark.asyncio
async def test_observation_bridge_routes_only_through_the_owned_service(
    tmp_path,
) -> None:
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
        {
            "id": "observe-1",
            "method": "observation.analyze",
            "payload": {"frame_id": "frame-1"},
        },
        emit_event=Mock(),
    )
    remembered = await service.handle(
        {
            "id": "observe-2",
            "method": "observation.remember",
            "payload": {"summary": "共同经历"},
        },
        emit_event=Mock(),
    )

    assert analyzed.error is None
    assert analyzed.payload == {"frame_id": "frame-1"}
    assert remembered.error is None
    assert remembered.payload == {"item_id": "event-1"}
    observation.analyze.assert_awaited_once()
    observation.remember.assert_awaited_once()


@pytest.mark.asyncio
async def test_chat_send_returns_busy_before_persisting_second_message(
    tmp_path,
) -> None:
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
async def test_chat_send_preserves_voice_turn_identity_in_metadata(tmp_path) -> None:
    role_store = RoleStore(tmp_path)
    role_store.create_role(
        role_id="mira",
        name="Mira",
        system_prompt="You are Mira.",
    )
    service = DesktopBridgeService(
        workspace=tmp_path,
        role_store=role_store,
        session_manager=SessionManager(tmp_path),
        agent_loop=SimpleNamespace(),
        event_bus=EventBus(),
    )
    service._start_chat_turn = Mock()

    response = await service.handle(
        {
            "id": "request-voice-1",
            "method": "chat.send",
            "payload": {
                "role_id": "mira",
                "content": "你好",
                "input_method": "voice",
                "voice_turn_id": "voice-turn-1",
                "asr_metrics": {
                    "provider": "tencent",
                    "request_id": "asr-request-1",
                    "elapsed_ms": 120,
                    "audio_duration_ms": 1000,
                    "character_count": 2,
                    "error_code": "",
                    "ignored": "raw-provider-field",
                },
            },
        },
        emit_event=Mock(),
    )

    assert response.error is None
    metadata = service._start_chat_turn.call_args.kwargs["metadata"]
    assert metadata["voice_turn_id"] == "voice-turn-1"
    assert metadata["asr_metrics"] == {
        "provider": "tencent",
        "request_id": "asr-request-1",
        "elapsed_ms": 120,
        "audio_duration_ms": 1000,
        "character_count": 2,
        "error_code": "",
    }


@pytest.mark.asyncio
async def test_voice_transcribe_returns_structured_metrics(tmp_path) -> None:
    service = DesktopBridgeService(
        workspace=tmp_path,
        role_store=RoleStore(tmp_path),
        session_manager=SessionManager(tmp_path),
        agent_loop=SimpleNamespace(),
        event_bus=EventBus(),
    )
    service.voice_service.transcribe_result = Mock(
        return_value=VoiceTranscriptionResult(
            text="你好",
            metrics=VoiceOperationMetrics(
                provider="tencent",
                request_id="asr-request-1",
                elapsed_ms=120,
                audio_duration_ms=1000,
                character_count=2,
            ),
        )
    )

    response = await service.handle(
        {
            "id": "request-asr-1",
            "method": "voice.transcribe",
            "payload": {"audio_base64": "AA=="},
        },
        emit_event=Mock(),
    )

    assert response.error is None
    assert response.payload == {
        "text": "你好",
        "metrics": {
            "provider": "tencent",
            "request_id": "asr-request-1",
            "elapsed_ms": 120,
            "audio_duration_ms": 1000,
            "character_count": 2,
            "error_code": "",
        },
    }


@pytest.mark.asyncio
async def test_voice_transcribe_error_returns_structured_metrics(tmp_path) -> None:
    service = DesktopBridgeService(
        workspace=tmp_path,
        role_store=RoleStore(tmp_path),
        session_manager=SessionManager(tmp_path),
        agent_loop=SimpleNamespace(),
        event_bus=EventBus(),
    )
    metrics = VoiceOperationMetrics(
        provider="tencent",
        request_id="asr-request-error",
        elapsed_ms=80,
        audio_duration_ms=900,
        character_count=0,
        error_code="FailedOperation.ServiceIsolate",
    )
    service.voice_service.transcribe_result = Mock(
        side_effect=VoiceServiceError("failed", metrics=metrics)
    )

    response = await service.handle(
        {
            "id": "request-asr-error",
            "method": "voice.transcribe",
            "payload": {"audio_base64": "AA=="},
        },
        emit_event=Mock(),
    )

    assert response.error is not None
    assert response.error.code == "voice_service_error"
    assert response.error.details == {"metrics": metrics.to_dict()}


@pytest.mark.asyncio
async def test_voice_provider_call_does_not_block_bridge_event_loop(tmp_path) -> None:
    started = threading.Event()
    release = threading.Event()
    service = DesktopBridgeService(
        workspace=tmp_path,
        role_store=RoleStore(tmp_path),
        session_manager=SessionManager(tmp_path),
        agent_loop=SimpleNamespace(),
        event_bus=EventBus(),
    )

    def transcribe(_audio: bytes) -> VoiceTranscriptionResult:
        started.set()
        release.wait(timeout=2)
        return VoiceTranscriptionResult(
            text="你好",
            metrics=VoiceOperationMetrics(
                provider="tencent",
                request_id="asr-threaded",
                elapsed_ms=10,
                audio_duration_ms=100,
                character_count=2,
            ),
        )

    service.voice_service.transcribe_result = transcribe
    task = asyncio.create_task(
        service.handle(
            {
                "id": "request-asr-threaded",
                "method": "voice.transcribe",
                "payload": {"audio_base64": "AA=="},
            },
            emit_event=Mock(),
        )
    )
    await asyncio.to_thread(started.wait, 1)
    await asyncio.sleep(0)
    assert not task.done()
    release.set()
    response = await task

    assert response.error is None
    assert response.payload["text"] == "你好"


@pytest.mark.asyncio
async def test_voice_turn_cancel_targets_only_the_requested_turn(tmp_path) -> None:
    service = DesktopBridgeService(
        workspace=tmp_path,
        role_store=RoleStore(tmp_path),
        session_manager=SessionManager(tmp_path),
        agent_loop=SimpleNamespace(),
        event_bus=EventBus(),
    )
    service.chat_service.cancel_voice_turn = Mock(return_value=True)

    response = await service.handle(
        {
            "id": "request-cancel-1",
            "method": "voice.turn.cancel",
            "payload": {"voice_turn_id": "voice-turn-1"},
        },
        emit_event=Mock(),
    )

    assert response.error is None
    assert response.payload == {"cancelled": True, "voice_turn_id": "voice-turn-1"}
    service.chat_service.cancel_voice_turn.assert_called_once_with("voice-turn-1")


@pytest.mark.asyncio
async def test_voice_delete_preserves_provider_and_ownership_guard(tmp_path) -> None:
    service = DesktopBridgeService(
        workspace=tmp_path,
        role_store=RoleStore(tmp_path),
        session_manager=SessionManager(tmp_path),
        agent_loop=SimpleNamespace(),
        event_bus=EventBus(),
    )
    service.voice_service.delete_managed_voice = Mock()

    response = await service.handle(
        {
            "id": "request-delete-voice-1",
            "method": "voice.delete",
            "payload": {
                "provider": "minimax",
                "voice_id": "Shiori_voice123",
                "ownership": "shiori_managed",
            },
        },
        emit_event=Mock(),
    )

    assert response.error is None
    assert response.payload == {"deleted": True}
    service.voice_service.delete_managed_voice.assert_called_once_with(
        provider="minimax",
        voice_id="Shiori_voice123",
        ownership="shiori_managed",
    )


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
async def test_external_proactive_media_commit_broadcasts_role_session(
    tmp_path,
) -> None:
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
    assert emitted[0]["payload"]["message"]["media"] == [
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
    assert emitted[0]["payload"]["message"]["media"] == [image]


@pytest.mark.asyncio
async def test_session_read_bridge_methods_return_bounded_desktop_projections(
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
    session.add_message("user", "最早的消息")
    session.add_message("assistant", "搜索天气")
    session.add_message("user", "最新的消息")
    session_manager.save(session)
    service = DesktopBridgeService(
        workspace=tmp_path,
        role_store=role_store,
        session_manager=session_manager,
        agent_loop=SimpleNamespace(),
        event_bus=EventBus(),
    )

    page = await service.handle(
        {
            "id": "page-1",
            "method": "session.messagesPage",
            "payload": {"role_id": "mira", "limit": 2},
        },
        emit_event=Mock(),
    )
    search = await service.handle(
        {
            "id": "search-1",
            "method": "session.search",
            "payload": {"role_id": "mira", "query": "天气"},
        },
        emit_event=Mock(),
    )
    around = await service.handle(
        {
            "id": "around-1",
            "method": "session.messagesAround",
            "payload": {"message_id": "role:mira:1", "context": 1},
        },
        emit_event=Mock(),
    )
    image_history = await service.handle(
        {
            "id": "image-history-1",
            "method": "session.imageHistory",
            "payload": {"role_id": "mira"},
        },
        emit_event=Mock(),
    )

    assert page.error is None
    assert [message["seq"] for message in page.payload["page"]["messages"]] == [1, 2]
    assert page.payload["page"]["has_more"] is True
    assert search.payload["results"] == [{
        "id": "role:mira:1",
        "session_key": "role:mira",
        "seq": 1,
        "role": "assistant",
        "timestamp": session.messages[1]["timestamp"],
        "preview": "搜索天气",
    }]
    assert search.payload["has_more"] is False
    assert [message["seq"] for message in around.payload["around"]["messages"]] == [0, 1, 2]
    assert around.payload["around"]["messages"][1]["is_target"] is True
    around_without_context = await service.handle(
        {
            "id": "around-zero-context",
            "method": "session.messagesAround",
            "payload": {"message_id": "role:mira:1", "context": 0},
        },
        emit_event=Mock(),
    )
    assert around_without_context.error is None
    assert [message["seq"] for message in around_without_context.payload["around"]["messages"]] == [1]
    assert image_history.error is None
    assert image_history.payload == {"session_key": "role:mira", "messages": []}

    missing = await service.handle(
        {
            "id": "around-missing",
            "method": "session.messagesAround",
            "payload": {"message_id": "role:mira:missing"},
        },
        emit_event=Mock(),
    )
    assert missing.error is not None
    assert missing.error.code == "invalid_request"

    other_session = session_manager.get_or_create("role:other")
    other_session.add_message("assistant", "other role message")
    session_manager.save(other_session)
    mismatched = await service.handle(
        {
            "id": "around-mismatch",
            "method": "session.messagesAround",
            "payload": {"role_id": "mira", "message_id": "role:other:0"},
        },
        emit_event=Mock(),
    )
    assert mismatched.error is not None
    assert mismatched.error.code == "invalid_request"
    assert mismatched.error.message == "message_id 不属于指定会话"

    invalid_page = await service.handle(
        {
            "id": "page-mismatch",
            "method": "session.messagesPage",
            "payload": {"role_id": "mira", "session_key": "role:other"},
        },
        emit_event=Mock(),
    )
    assert invalid_page.error is not None
    assert invalid_page.error.code == "invalid_request"


@pytest.mark.asyncio
async def test_session_image_history_returns_media_only_projection(tmp_path) -> None:
    role_store = RoleStore(tmp_path)
    role_store.create_role(
        role_id="mira",
        name="Mira",
        system_prompt="You are Mira.",
    )
    session_manager = SessionManager(tmp_path)
    session = session_manager.get_or_create("role:mira")
    session.add_message("assistant", "旧图片", media=["D:\\images\\old.png"])
    session.add_message("assistant", "最新文本")
    session_manager.save(session)
    service = DesktopBridgeService(
        workspace=tmp_path,
        role_store=role_store,
        session_manager=session_manager,
        agent_loop=SimpleNamespace(),
        event_bus=EventBus(),
    )

    response = await service.handle(
        {
            "id": "image-history-1",
            "method": "session.imageHistory",
            "payload": {"role_id": "mira"},
        },
        emit_event=Mock(),
    )

    assert response.error is None
    assert response.payload["session_key"] == "role:mira"
    assert response.payload["messages"] == [{
        "id": "role:mira:0",
        "seq": 0,
        "timestamp": session.messages[0]["timestamp"],
        "media": ["D:\\images\\old.png"],
    }]
