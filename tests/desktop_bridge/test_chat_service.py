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
)
from desktop_bridge.chat_service import ChatTurnBusyError, DesktopChatService
from desktop_bridge.voice_service import VoiceOperationMetrics, VoiceSynthesisResult


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


@pytest.mark.asyncio
async def test_chat_service_bridges_tool_call_lifecycle_for_current_session() -> None:
    event_bus = EventBus()
    emitted: list[dict] = []

    async def _process_direct(*_args, **_kwargs) -> None:
        await event_bus.observe(ToolCallStarted(
            session_key="role:role-1",
            channel="desktop",
            chat_id="role:role-1",
            iteration=1,
            call_id="call-1",
            tool_name="web_search",
            arguments={"query": "天气"},
        ))
        await event_bus.observe(ToolCallStarted(
            session_key="role:other",
            channel="desktop",
            chat_id="role:other",
            iteration=1,
            call_id="other",
            tool_name="shell",
            arguments={},
        ))
        await event_bus.observe(ToolCallCompleted(
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
        ))

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

    tool_events = [event for event in emitted if event["method"].startswith("chat.tool.")]
    assert [event["method"] for event in tool_events] == [
        "chat.tool.started",
        "chat.tool.completed",
    ]
    assert tool_events[0]["payload"] == {
        "session_key": "role:role-1",
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
        await event_bus.observe(ToolCallCompleted(
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
        ))

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
async def test_chat_service_does_not_bridge_live_tool_events_when_streaming_disabled() -> None:
    event_bus = EventBus()
    emitted: list[dict] = []

    async def _process_direct(*_args, **_kwargs) -> None:
        await event_bus.observe(ToolCallStarted(
            session_key="role:role-1",
            channel="desktop",
            chat_id="role:role-1",
            iteration=1,
            call_id="call-1",
            tool_name="web_search",
            arguments={"query": "天气"},
        ))

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

    assert [
        event["method"] for event in emitted if event["method"].startswith("voice.")
    ] == ["voice.reply.started", "voice.tts.finished"]
