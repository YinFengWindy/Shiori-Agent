from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from bus.event_bus import EventBus
from bus.events_lifecycle import (
    StreamDeltaReady,
    ToolCallCompleted,
    ToolCallStarted,
    TurnCommitted,
    TurnFailed,
)
from desktop_bridge.chat_service import ChatTurnBusyError, DesktopChatService
from desktop_bridge.voice.voice_service import (
    VoiceOperationMetrics,
    VoiceSynthesisResult,
)
from agent.looping.interrupt import TurnInterruptState
from session.manager import Session
from session.manager.models import INTERRUPTED_TURN_METADATA_KEY


class _VoiceService:
    tts_enabled = True
    tts_provider = "minimax"

    def __init__(self) -> None:
        self.calls: list[str] = []

    def stream_synthesize_result(
        self,
        text: str,
        *,
        voice_id: str,
        speed: float,
        emotion: str,
        cancel_event=None,
    ) -> VoiceSynthesisResult:
        del voice_id, speed, emotion, cancel_event
        self.calls.append(text)
        return VoiceSynthesisResult(
            audio=text.encode("utf-8"),
            metrics=VoiceOperationMetrics(
                provider="minimax",
                request_id=f"tts-{len(self.calls)}",
                elapsed_ms=10,
                audio_duration_ms=500,
                character_count=len(text),
            ),
        )


async def test_desktop_chat_update_includes_ordered_intermediate_tool_pushes():
    bus = EventBus()
    session = Session(key="role:mira")
    for message_id, role, content in [
        ("old", "assistant", "old"),
        ("user", "user", "request"),
        ("push", "assistant", "push"),
        ("reply", "assistant", "reply"),
    ]:
        session.add_message(role, content, id=message_id)

    async def process_direct(*_args, **_kwargs):
        await bus.fanout(
            TurnCommitted(
                session_key=session.key,
                channel="desktop",
                chat_id=session.key,
                input_message="request",
                persisted_user_message="request",
                assistant_response="reply",
                tools_used=["message_push"],
                extra={"committed_message_ids": ["user", "push", "reply"]},
            )
        )
        return "reply"

    async def emit_payload(emit_event, payload):
        emit_event(payload)

    async def emit_session_updated(*, request_id, session, emit_event, messages=None):
        assert messages is not None
        emit_event({"method": "session.updated", "payload": {"messages": messages}})

    service = DesktopChatService(
        agent_loop=SimpleNamespace(process_direct=process_direct),
        event_bus=bus,
        session_manager=SimpleNamespace(get_or_create=Mock(return_value=session)),
        role_id_from_session_key=lambda _key: "mira",
        sync_desktop_session_thread=Mock(),
        emit_payload=emit_payload,
        emit_session_updated=emit_session_updated,
    )
    emitted = []
    await service.run_chat_turn(
        request_id="request",
        turn_id="turn",
        session_key=session.key,
        content="request",
        media=[],
        metadata={},
        omit_user_turn=False,
        emit_event=emitted.append,
    )
    update = next(event for event in emitted if event["method"] == "session.updated")
    assert [message["id"] for message in update["payload"]["messages"]] == [
        "user",
        "push",
        "reply",
    ]


@pytest.mark.asyncio
async def test_chat_service_bridges_tool_call_lifecycle_for_current_session() -> None:
    event_bus = EventBus()
    emitted: list[dict] = []

    async def _process_direct(*_args, **_kwargs) -> None:
        await event_bus.observe(
            ToolCallStarted(
                session_key="role:role-1",
                channel="desktop",
                chat_id="role:role-1",
                iteration=1,
                call_id="call-1",
                tool_name="web_search",
                arguments={"query": "天气"},
            )
        )
        await event_bus.observe(
            ToolCallStarted(
                session_key="role:other",
                channel="desktop",
                chat_id="role:other",
                iteration=1,
                call_id="other",
                tool_name="shell",
                arguments={},
            )
        )
        await event_bus.observe(
            ToolCallCompleted(
                session_key="role:role-1",
                channel="desktop",
                chat_id="role:role-1",
                iteration=1,
                call_id="call-1",
                tool_name="web_search",
                arguments={"query": "天气"},
                final_arguments={"query": "上海天气"},
                status="success",
                result_preview="晴，28°C",
            )
        )

    async def _emit_payload(_emit_event, payload: dict) -> None:
        emitted.append(payload)

    service = DesktopChatService(
        agent_loop=SimpleNamespace(process_direct=_process_direct),
        event_bus=event_bus,
        session_manager=SimpleNamespace(
            get_or_create=Mock(return_value=SimpleNamespace(metadata={}))
        ),
        role_id_from_session_key=Mock(return_value="role-1"),
        sync_desktop_session_thread=Mock(),
        emit_payload=_emit_payload,
        emit_session_updated=AsyncMock(),
        streaming_enabled=True,
    )

    await service.run_chat_turn(
        request_id="request-tools",
        session_key="role:role-1",
        content="查天气",
        media=[],
        metadata={},
        omit_user_turn=True,
        emit_event=AsyncMock(),
    )

    tool_events = [
        event for event in emitted if event["method"].startswith("chat.tool.")
    ]
    assert [event["method"] for event in tool_events] == [
        "chat.tool.started",
        "chat.tool.completed",
    ]
    assert tool_events[0]["payload"] == {
        "session_key": "role:role-1",
        "turn_id": "request-tools",
        "iteration": 1,
        "call_id": "call-1",
        "tool_name": "web_search",
        "arguments": {"query": "天气"},
    }
    assert tool_events[1]["payload"]["final_arguments"] == {"query": "上海天气"}
    assert tool_events[1]["payload"]["result_preview"] == "晴，28°C"
    assert event_bus._handlers == {}


@pytest.mark.asyncio
async def test_chat_service_truncates_tool_result_preview_for_desktop() -> None:
    event_bus = EventBus()
    emitted: list[dict] = []

    async def _process_direct(*_args, **_kwargs) -> None:
        await event_bus.observe(
            ToolCallCompleted(
                session_key="role:role-1",
                channel="desktop",
                chat_id="role:role-1",
                iteration=1,
                call_id="call-1",
                tool_name="read_file",
                arguments={},
                final_arguments={},
                status="success",
                result_preview="x" * 2500,
            )
        )

    async def _emit_payload(_emit_event, payload: dict) -> None:
        emitted.append(payload)

    service = DesktopChatService(
        agent_loop=SimpleNamespace(process_direct=_process_direct),
        event_bus=event_bus,
        session_manager=SimpleNamespace(
            get_or_create=Mock(return_value=SimpleNamespace(metadata={}))
        ),
        role_id_from_session_key=Mock(return_value="role-1"),
        sync_desktop_session_thread=Mock(),
        emit_payload=_emit_payload,
        emit_session_updated=AsyncMock(),
        streaming_enabled=True,
    )

    await service.run_chat_turn(
        request_id="request-long-tool-result",
        session_key="role:role-1",
        content="读取文件",
        media=[],
        metadata={},
        omit_user_turn=True,
        emit_event=AsyncMock(),
    )

    completed = next(
        event for event in emitted if event["method"] == "chat.tool.completed"
    )
    preview = completed["payload"]["result_preview"]
    assert len(preview) == 2000
    assert preview.endswith("...")


@pytest.mark.asyncio
async def test_chat_service_does_not_bridge_live_tool_events_when_streaming_disabled() -> (
    None
):
    event_bus = EventBus()
    emitted: list[dict] = []

    async def _process_direct(*_args, **_kwargs) -> None:
        await event_bus.observe(
            ToolCallStarted(
                session_key="role:role-1",
                channel="desktop",
                chat_id="role:role-1",
                iteration=1,
                call_id="call-1",
                tool_name="web_search",
                arguments={"query": "天气"},
            )
        )

    async def _emit_payload(_emit_event, payload: dict) -> None:
        emitted.append(payload)

    service = DesktopChatService(
        agent_loop=SimpleNamespace(process_direct=_process_direct),
        event_bus=event_bus,
        session_manager=SimpleNamespace(
            get_or_create=Mock(return_value=SimpleNamespace(metadata={}))
        ),
        role_id_from_session_key=Mock(return_value="role-1"),
        sync_desktop_session_thread=Mock(),
        emit_payload=_emit_payload,
        emit_session_updated=AsyncMock(),
        streaming_enabled=False,
    )

    await service.run_chat_turn(
        request_id="request-tools-disabled",
        session_key="role:role-1",
        content="查天气",
        media=[],
        metadata={},
        omit_user_turn=True,
        emit_event=AsyncMock(),
    )

    assert not any(event["method"].startswith("chat.tool.") for event in emitted)


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
async def test_cancel_chat_turn_interrupts_only_the_matching_session_and_turn() -> None:
    started = asyncio.Event()
    interrupt = Mock(
        return_value=SimpleNamespace(
            status="interrupted",
            session_key="role:role-1",
            message="cancelled",
        )
    )

    async def _process_direct(*_args, **_kwargs) -> None:
        started.set()
        await asyncio.Event().wait()

    service = DesktopChatService(
        agent_loop=SimpleNamespace(
            process_direct=_process_direct,
            request_interrupt=interrupt,
        ),
        event_bus=EventBus(),
        session_manager=SimpleNamespace(get_or_create=Mock()),
        role_id_from_session_key=Mock(return_value="role-1"),
        sync_desktop_session_thread=Mock(),
        emit_payload=AsyncMock(),
        emit_session_updated=AsyncMock(),
    )
    service.start_chat_turn(
        request_id="request-1",
        turn_id="turn-current",
        session_key="role:role-1",
        content="hello",
        media=[],
        metadata={},
        omit_user_turn=True,
        emit_event=AsyncMock(),
    )
    await started.wait()

    wrong_session = service.cancel_chat_turn("role:other", "turn-current")
    wrong_turn = service.cancel_chat_turn("role:role-1", "turn-old")

    assert wrong_session.status == "idle"
    assert wrong_turn.status == "mismatch"
    assert service.is_busy("role:role-1") is True
    interrupt.assert_not_called()

    result = service.cancel_chat_turn("role:role-1", "turn-current")

    assert result.status == "interrupted"
    interrupt.assert_called_once_with(
        "role:role-1",
        sender="desktop",
        command="/cancel",
    )
    await asyncio.sleep(0)
    assert service.is_busy("role:role-1") is False
    await service.aclose()


@pytest.mark.asyncio
async def test_cancel_chat_turn_waits_for_old_listener_cleanup_before_follow_up() -> (
    None
):
    started = asyncio.Event()
    cleanup_started = asyncio.Event()
    release_cleanup = asyncio.Event()
    calls = 0

    async def _process_direct(*_args, **_kwargs) -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                cleanup_started.set()
                await release_cleanup.wait()

    service = DesktopChatService(
        agent_loop=SimpleNamespace(
            process_direct=_process_direct,
            request_interrupt=Mock(
                return_value=SimpleNamespace(status="interrupted", message="cancelled")
            ),
        ),
        event_bus=EventBus(),
        session_manager=SimpleNamespace(get_or_create=Mock()),
        role_id_from_session_key=Mock(return_value="role-1"),
        sync_desktop_session_thread=Mock(),
        emit_payload=AsyncMock(),
        emit_session_updated=AsyncMock(),
    )
    arguments = {
        "request_id": "request-1",
        "turn_id": "turn-1",
        "session_key": "role:role-1",
        "content": "first",
        "media": [],
        "metadata": {},
        "omit_user_turn": True,
        "emit_event": AsyncMock(),
    }
    service.start_chat_turn(**arguments)
    await started.wait()

    cancel_task = asyncio.create_task(
        service.cancel_chat_turn_async("role:role-1", "turn-1")
    )
    await cleanup_started.wait()

    with pytest.raises(ChatTurnBusyError):
        service.start_chat_turn(
            **{
                **arguments,
                "request_id": "request-2",
                "turn_id": "turn-2",
                "content": "follow up",
            }
        )

    release_cleanup.set()
    result = await cancel_task

    assert result.status == "interrupted"
    service.start_chat_turn(
        **{
            **arguments,
            "request_id": "request-2",
            "turn_id": "turn-2",
            "content": "follow up",
        }
    )
    await asyncio.sleep(0)
    assert calls == 2
    await service.aclose()


@pytest.mark.asyncio
async def test_cancel_chat_turn_keeps_naturally_completed_turn_when_interrupt_is_idle() -> (
    None
):
    process_completed = asyncio.Event()
    session_update_started = asyncio.Event()
    session_update_completed = asyncio.Event()
    release_session_update = asyncio.Event()

    async def _process_direct(*_args, **_kwargs) -> None:
        process_completed.set()

    async def _emit_session_updated(**_kwargs) -> None:
        session_update_started.set()
        await release_session_update.wait()
        session_update_completed.set()

    service = DesktopChatService(
        agent_loop=SimpleNamespace(
            process_direct=_process_direct,
            request_interrupt=Mock(
                return_value=SimpleNamespace(
                    status="idle",
                    message="turn already completed",
                )
            ),
        ),
        event_bus=EventBus(),
        session_manager=SimpleNamespace(get_or_create=Mock()),
        role_id_from_session_key=Mock(return_value="role-1"),
        sync_desktop_session_thread=Mock(),
        emit_payload=AsyncMock(),
        emit_session_updated=_emit_session_updated,
    )
    service.start_chat_turn(
        request_id="request-1",
        turn_id="turn-1",
        session_key="role:role-1",
        content="hello",
        media=[],
        metadata={},
        omit_user_turn=True,
        emit_event=AsyncMock(),
    )
    await process_completed.wait()
    await session_update_started.wait()

    cancel_task = asyncio.create_task(
        service.cancel_chat_turn_async("role:role-1", "turn-1")
    )
    await asyncio.sleep(0)

    assert cancel_task.done() is False
    release_session_update.set()
    result = await cancel_task

    assert result.status == "idle"
    assert session_update_completed.is_set()
    await service.aclose()


@pytest.mark.asyncio
async def test_cancel_chat_turn_stops_the_associated_voice_tts_coordinator() -> None:
    started = asyncio.Event()

    async def _process_direct(*_args, **_kwargs) -> None:
        started.set()
        await asyncio.Event().wait()

    service = DesktopChatService(
        agent_loop=SimpleNamespace(
            process_direct=_process_direct,
            request_interrupt=Mock(
                return_value=SimpleNamespace(status="interrupted", message="cancelled")
            ),
        ),
        event_bus=EventBus(),
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
        tts_service=SimpleNamespace(
            tts_enabled=True,
            tts_provider="minimax",
            stream_synthesize_result=Mock(),
        ),
    )
    service.start_chat_turn(
        request_id="request-voice-1",
        turn_id="turn-voice",
        session_key="role:role-1",
        content="hello",
        media=[],
        metadata={"input_method": "voice", "voice_turn_id": "voice-turn-1"},
        omit_user_turn=True,
        emit_event=AsyncMock(),
    )
    await started.wait()
    coordinator = Mock()
    service._tts_coordinators["voice-turn-1"] = coordinator

    result = service.cancel_chat_turn("role:role-1", "turn-voice")

    assert result.status == "interrupted"
    coordinator.cancel.assert_called_once_with()
    await asyncio.sleep(0)
    await service.aclose()


@pytest.mark.asyncio
async def test_cancel_chat_turn_persists_partial_reply_and_reasoning() -> None:
    started = asyncio.Event()
    session = Session("role:role-1")
    interrupt_state = TurnInterruptState(
        session_key=session.key,
        original_user_message="hello",
        partial_reply="partial answer",
        partial_thinking="retain this reasoning",
        tools_used=["web_search"],
        tool_chain_partial=[
            {
                "text": "",
                "calls": [
                    {
                        "call_id": "call-1",
                        "name": "web_search",
                        "arguments": {"query": "weather"},
                        "result": "sunny",
                    }
                ],
            }
        ],
    )

    async def _process_direct(*_args, **_kwargs) -> None:
        started.set()
        await asyncio.Event().wait()

    session_manager = SimpleNamespace(
        get_or_create=Mock(return_value=session),
        append_messages=AsyncMock(),
    )
    service = DesktopChatService(
        agent_loop=SimpleNamespace(
            process_direct=_process_direct,
            request_interrupt=Mock(
                return_value=SimpleNamespace(
                    status="interrupted",
                    message="cancelled",
                    state=interrupt_state,
                )
            ),
            discard_interrupt_state=Mock(),
        ),
        event_bus=EventBus(),
        session_manager=session_manager,
        role_id_from_session_key=Mock(return_value="role-1"),
        sync_desktop_session_thread=Mock(),
        emit_payload=AsyncMock(),
        emit_session_updated=AsyncMock(),
    )
    service.start_chat_turn(
        request_id="request-1",
        turn_id="turn-1",
        session_key=session.key,
        content="hello",
        media=[],
        metadata={},
        omit_user_turn=True,
        emit_event=AsyncMock(),
    )
    await started.wait()

    result = await service.cancel_chat_turn_async(session.key, "turn-1")

    assert result.status == "interrupted"
    assistant = session.messages[-1]
    assert assistant["role"] == "assistant"
    assert assistant["content"] == "partial answer"
    assert assistant["reasoning_content"] == "retain this reasoning"
    assert assistant["metadata"]["interrupted_reply"] is True
    assert session.metadata[INTERRUPTED_TURN_METADATA_KEY]["turn_id"] == "turn-1"
    session_manager.append_messages.assert_awaited_once_with(session, [assistant])
    await service.aclose()


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
async def test_cancel_voice_turn_rejects_late_tts_delta() -> None:
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


@pytest.mark.asyncio
async def test_non_streamed_voice_reply_synthesizes_final_response() -> None:
    event_bus = EventBus()
    tts_service = _VoiceService()
    emitted: list[dict] = []
    session = SimpleNamespace(
        metadata={"role_runtime_config": {"tts": {"voice_id": "mira"}}}
    )

    async def _process_direct(*_args, **_kwargs) -> None:
        await event_bus.observe(
            TurnCommitted(
                session_key="role:role-1",
                channel="desktop",
                chat_id="role:role-1",
                input_message="hello",
                persisted_user_message=None,
                assistant_response="完整回复。",
                tools_used=[],
                total_tokens=2438,
                thinking_duration_ms=6200,
            )
        )

    async def _emit_payload(_emit_event, payload: dict) -> None:
        emitted.append(payload)

    service = DesktopChatService(
        agent_loop=SimpleNamespace(process_direct=_process_direct),
        event_bus=event_bus,
        session_manager=SimpleNamespace(get_or_create=Mock(return_value=session)),
        role_id_from_session_key=Mock(return_value="role-1"),
        sync_desktop_session_thread=Mock(),
        emit_payload=_emit_payload,
        emit_session_updated=AsyncMock(),
        tts_service=tts_service,  # type: ignore[arg-type]
    )

    await service.run_chat_turn(
        request_id="request-voice-final",
        session_key="role:role-1",
        content="hello",
        media=[],
        metadata={"input_method": "voice", "voice_turn_id": "voice-turn-final"},
        omit_user_turn=True,
        emit_event=AsyncMock(),
    )
    await service.wait_for_tts()

    assert tts_service.calls == ["完整回复。"]
    done = next(event for event in emitted if event["method"] == "chat.done")
    assert done["payload"]["total_tokens"] == 2438
    assert done["payload"]["thinking_duration_ms"] == 6200
    assert [
        event["method"] for event in emitted if event["method"].startswith("voice.")
    ] == [
        "voice.reply.started",
        "voice.tts.audio",
        "voice.tts.finished",
    ]


@pytest.mark.asyncio
async def test_streamed_voice_reply_does_not_synthesize_final_response_twice() -> None:
    event_bus = EventBus()
    tts_service = _VoiceService()
    session = SimpleNamespace(
        metadata={"role_runtime_config": {"tts": {"voice_id": "mira"}}}
    )

    async def _process_direct(*_args, **_kwargs) -> None:
        await event_bus.observe(
            StreamDeltaReady(
                session_key="role:role-1",
                channel="desktop",
                chat_id="role:role-1",
                content_delta="流式回复。",
            )
        )
        await event_bus.observe(
            TurnCommitted(
                session_key="role:role-1",
                channel="desktop",
                chat_id="role:role-1",
                input_message="hello",
                persisted_user_message=None,
                assistant_response="流式回复。",
                tools_used=[],
            )
        )

    service = DesktopChatService(
        agent_loop=SimpleNamespace(process_direct=_process_direct),
        event_bus=event_bus,
        session_manager=SimpleNamespace(get_or_create=Mock(return_value=session)),
        role_id_from_session_key=Mock(return_value="role-1"),
        sync_desktop_session_thread=Mock(),
        emit_payload=AsyncMock(),
        emit_session_updated=AsyncMock(),
        tts_service=tts_service,  # type: ignore[arg-type]
    )

    await service.run_chat_turn(
        request_id="request-voice-stream",
        session_key="role:role-1",
        content="hello",
        media=[],
        metadata={"input_method": "voice", "voice_turn_id": "voice-turn-stream"},
        omit_user_turn=True,
        emit_event=AsyncMock(),
    )
    await service.wait_for_tts()

    assert tts_service.calls == ["流式回复。"]


@pytest.mark.asyncio
async def test_voice_reply_finishes_when_tts_is_disabled() -> None:
    event_bus = EventBus()
    tts_service = _VoiceService()
    tts_service.tts_enabled = False
    emitted: list[dict] = []

    async def _emit_payload(_emit_event, payload: dict) -> None:
        emitted.append(payload)

    service = DesktopChatService(
        agent_loop=SimpleNamespace(process_direct=AsyncMock()),
        event_bus=event_bus,
        session_manager=SimpleNamespace(
            get_or_create=Mock(return_value=SimpleNamespace(metadata={}))
        ),
        role_id_from_session_key=Mock(return_value="role-1"),
        sync_desktop_session_thread=Mock(),
        emit_payload=_emit_payload,
        emit_session_updated=AsyncMock(),
        tts_service=tts_service,  # type: ignore[arg-type]
    )

    await service.run_chat_turn(
        request_id="request-voice-disabled",
        session_key="role:role-1",
        content="hello",
        media=[],
        metadata={"input_method": "voice", "voice_turn_id": "voice-turn-disabled"},
        omit_user_turn=True,
        emit_event=AsyncMock(),
    )
    await service.wait_for_tts()

    voice_events = [event for event in emitted if event["method"].startswith("voice.")]
    assert [event["method"] for event in voice_events] == [
        "voice.reply.started",
        "voice.tts.finished",
    ]
    assert voice_events[0]["payload"]["has_voice"] is False


@pytest.mark.asyncio
async def test_chat_service_disables_model_stream_events_from_config() -> None:
    event_bus = EventBus()
    process_direct = AsyncMock()
    service = DesktopChatService(
        agent_loop=SimpleNamespace(process_direct=process_direct),
        event_bus=event_bus,
        session_manager=SimpleNamespace(
            get_or_create=Mock(return_value=SimpleNamespace(metadata={}))
        ),
        role_id_from_session_key=Mock(return_value="role-1"),
        sync_desktop_session_thread=Mock(),
        emit_payload=AsyncMock(),
        emit_session_updated=AsyncMock(),
        streaming_enabled=False,
    )

    await service.run_chat_turn(
        request_id="request-no-stream",
        session_key="role:role-1",
        content="hello",
        media=[],
        metadata={},
        omit_user_turn=True,
        emit_event=AsyncMock(),
    )

    assert process_direct.await_args.kwargs["stream_events"] is False


@pytest.mark.asyncio
async def test_chat_failure_terminates_voice_lifecycle() -> None:
    emitted: list[dict] = []

    async def _emit_payload(_emit_event, payload: dict) -> None:
        emitted.append(payload)

    async def _process_direct(*_args, **_kwargs) -> None:
        raise RuntimeError("backend down")

    service = DesktopChatService(
        agent_loop=SimpleNamespace(process_direct=_process_direct),
        event_bus=EventBus(),
        session_manager=SimpleNamespace(
            get_or_create=Mock(
                return_value=SimpleNamespace(
                    metadata={"role_runtime_config": {"tts": {"voice_id": "mira"}}}
                )
            )
        ),
        role_id_from_session_key=Mock(return_value="role-1"),
        sync_desktop_session_thread=Mock(),
        emit_payload=_emit_payload,
        emit_session_updated=AsyncMock(),
        tts_service=_VoiceService(),  # type: ignore[arg-type]
    )

    with pytest.raises(RuntimeError, match="backend down"):
        await service.run_chat_turn(
            request_id="request-voice-error",
            session_key="role:role-1",
            content="hello",
            media=[],
            metadata={"input_method": "voice", "voice_turn_id": "voice-turn-error"},
            omit_user_turn=True,
            emit_event=AsyncMock(),
        )

    assert [
        event["method"] for event in emitted if event["method"].startswith("voice.")
    ] == ["voice.reply.started", "voice.tts.finished"]


@pytest.mark.asyncio
async def test_cancelled_chat_task_terminates_voice_lifecycle() -> None:
    started = asyncio.Event()
    emitted: list[dict] = []

    async def _emit_payload(_emit_event, payload: dict) -> None:
        emitted.append(payload)

    async def _process_direct(*_args, **_kwargs) -> None:
        started.set()
        await asyncio.Event().wait()

    service = DesktopChatService(
        agent_loop=SimpleNamespace(process_direct=_process_direct),
        event_bus=EventBus(),
        session_manager=SimpleNamespace(
            get_or_create=Mock(
                return_value=SimpleNamespace(
                    metadata={"role_runtime_config": {"tts": {"voice_id": "mira"}}}
                )
            )
        ),
        role_id_from_session_key=Mock(return_value="role-1"),
        sync_desktop_session_thread=Mock(),
        emit_payload=_emit_payload,
        emit_session_updated=AsyncMock(),
        tts_service=_VoiceService(),  # type: ignore[arg-type]
    )
    task = asyncio.create_task(
        service.run_chat_turn(
            request_id="request-voice-cancelled",
            session_key="role:role-1",
            content="hello",
            media=[],
            metadata={
                "input_method": "voice",
                "voice_turn_id": "voice-turn-cancelled",
            },
            omit_user_turn=True,
            emit_event=AsyncMock(),
        )
    )
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert not any(event["method"] in {"chat.done", "chat.error"} for event in emitted)
    assert [
        event["method"] for event in emitted if event["method"].startswith("voice.")
    ] == ["voice.reply.started", "voice.tts.finished"]


@pytest.mark.asyncio
@pytest.mark.parametrize("failure_stage", [None, "after_commit", "session_update"])
async def test_chat_terminal_waits_for_turn_and_session_work(failure_stage):
    event_bus = EventBus()
    emitted = []
    service = None

    async def process_direct(*_args, **_kwargs):
        await event_bus.fanout(
            TurnCommitted(
                session_key="role:mira",
                channel="desktop",
                chat_id="role:mira",
                input_message="hello",
                persisted_user_message=None,
                assistant_response="answer",
                tools_used=[],
            )
        )
        assert emitted == []
        if failure_stage == "after_commit":
            raise RuntimeError("after_commit failed")
        return "answer"

    async def emit_session_updated(*, request_id, session, emit_event, messages=None):
        assert emitted == []
        if failure_stage == "session_update":
            raise RuntimeError("session_update failed")
        emit_event(
            {"method": "session.updated", "payload": {"session_key": session.key}}
        )

    def collect(payload):
        assert not service.is_busy("role:mira")
        emitted.append(payload)

    async def emit_payload(emit_event, payload):
        result = emit_event(payload)
        if result is not None:
            await result

    service = DesktopChatService(
        agent_loop=SimpleNamespace(process_direct=process_direct),
        event_bus=event_bus,
        session_manager=SimpleNamespace(
            get_or_create=Mock(return_value=Session(key="role:mira"))
        ),
        role_id_from_session_key=lambda _key: "mira",
        sync_desktop_session_thread=Mock(),
        emit_payload=emit_payload,
        emit_session_updated=emit_session_updated,
    )
    service.start_chat_turn(
        request_id="request-1",
        turn_id="turn-1",
        session_key="role:mira",
        content="hello",
        media=[],
        metadata={},
        omit_user_turn=True,
        emit_event=collect,
    )
    await service.drain()

    expected = {
        None: ["chat.done", "session.updated"],
        "after_commit": ["session.updated", "chat.error"],
        "session_update": ["chat.error"],
    }
    assert [event["method"] for event in emitted] == expected[failure_stage]
    terminal = next(event for event in emitted if event["method"].startswith("chat."))
    assert terminal["payload"]["turn_id"] == "turn-1"
    if failure_stage:
        assert terminal["payload"]["message"] == f"{failure_stage} failed"
    assert event_bus._handlers == {}


@pytest.mark.asyncio
@pytest.mark.parametrize("failure_stage", ["session_lookup", "session_update"])
async def test_failure_snapshot_cannot_replace_original_error(failure_stage, caplog):
    original_error = RuntimeError("provider failed")
    snapshot_error = RuntimeError("snapshot unavailable")
    emitted = []
    event_bus = EventBus()
    lookup = Mock(return_value=Session(key="role:mira"))
    update = AsyncMock()
    if failure_stage == "session_lookup":
        lookup.side_effect = snapshot_error
    else:
        update.side_effect = snapshot_error

    async def emit_payload(emit_event, payload):
        result = emit_event(payload)
        if result is not None:
            await result

    service = DesktopChatService(
        agent_loop=SimpleNamespace(
            process_direct=AsyncMock(side_effect=original_error)
        ),
        event_bus=event_bus,
        session_manager=SimpleNamespace(get_or_create=lookup),
        role_id_from_session_key=lambda _key: "mira",
        sync_desktop_session_thread=Mock(),
        emit_payload=emit_payload,
        emit_session_updated=update,
    )
    with pytest.raises(RuntimeError) as raised:
        await service.run_chat_turn(
            request_id="request-1",
            turn_id="turn-1",
            session_key="role:mira",
            content="hello",
            media=[],
            metadata={},
            omit_user_turn=True,
            emit_event=emitted.append,
        )

    assert raised.value is original_error
    assert [event["method"] for event in emitted] == ["chat.error"]
    assert emitted[0]["payload"] == {
        "session_key": "role:mira",
        "turn_id": "turn-1",
        "message": "provider failed",
        "detail": "RuntimeError: provider failed",
    }
    assert "snapshot unavailable" in caplog.text
    assert event_bus._handlers == {}


@pytest.mark.asyncio
async def test_generic_turn_failure_reports_its_scrubbed_cause_as_detail():
    event_bus = EventBus()
    emitted = []

    async def process_direct(*_args, **_kwargs):
        # The pipeline swallows the exception, publishes its summary and
        # returns the generic reply without committing a turn.
        await event_bus.observe(
            TurnFailed(session_key="role:other", error_summary="Other: not this turn")
        )
        await event_bus.observe(
            TurnFailed(
                session_key="role:mira",
                error_summary="APIStatusError: 502 Bad Gateway",
            )
        )
        return "处理消息时出错，请稍后再试。"

    async def emit_payload(emit_event, payload):
        result = emit_event(payload)
        if result is not None:
            await result

    async def emit_session_updated(*, request_id, session, emit_event, messages=None):
        return None

    service = DesktopChatService(
        agent_loop=SimpleNamespace(process_direct=process_direct),
        event_bus=event_bus,
        session_manager=SimpleNamespace(
            get_or_create=Mock(return_value=Session(key="role:mira"))
        ),
        role_id_from_session_key=lambda _key: "mira",
        sync_desktop_session_thread=Mock(),
        emit_payload=emit_payload,
        emit_session_updated=emit_session_updated,
    )
    service.start_chat_turn(
        request_id="request-1",
        turn_id="turn-1",
        session_key="role:mira",
        content="hello",
        media=[],
        metadata={},
        omit_user_turn=True,
        emit_event=emitted.append,
    )
    await service.drain()

    terminal = next(event for event in emitted if event["method"] == "chat.error")
    assert terminal["payload"]["message"] == "处理消息时出错，请稍后再试。"
    assert terminal["payload"]["detail"] == "APIStatusError: 502 Bad Gateway"
    assert event_bus._handlers == {}


@pytest.mark.asyncio
async def test_raised_turn_failure_detail_is_scrubbed():
    event_bus = EventBus()
    emitted = []

    async def process_direct(*_args, **_kwargs):
        raise RuntimeError("401 Authorization: Bearer abcdefghijklmnopqrst")

    async def emit_payload(emit_event, payload):
        result = emit_event(payload)
        if result is not None:
            await result

    async def emit_session_updated(*, request_id, session, emit_event, messages=None):
        return None

    service = DesktopChatService(
        agent_loop=SimpleNamespace(process_direct=process_direct),
        event_bus=event_bus,
        session_manager=SimpleNamespace(
            get_or_create=Mock(return_value=Session(key="role:mira"))
        ),
        role_id_from_session_key=lambda _key: "mira",
        sync_desktop_session_thread=Mock(),
        emit_payload=emit_payload,
        emit_session_updated=emit_session_updated,
    )
    service.start_chat_turn(
        request_id="request-1",
        turn_id="turn-1",
        session_key="role:mira",
        content="hello",
        media=[],
        metadata={},
        omit_user_turn=True,
        emit_event=emitted.append,
    )
    await service.drain()

    terminal = next(event for event in emitted if event["method"] == "chat.error")
    assert "abcdefghijklmnopqrst" not in terminal["payload"]["detail"]
    assert terminal["payload"]["detail"].startswith("RuntimeError: 401")
