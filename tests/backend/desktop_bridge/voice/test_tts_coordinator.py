from __future__ import annotations

import asyncio
import threading

import pytest

from desktop_bridge.voice.role_tts_settings import (
    RoleTtsSettings,
    resolve_role_tts_settings,
)
from desktop_bridge.voice.tts_coordinator import TtsTurnCoordinator
from desktop_bridge.voice.voice_service import VoiceOperationMetrics, VoiceSynthesisResult


class _VoiceService:
    tts_provider = "minimax"

    def __init__(self, *, error: Exception | None = None) -> None:
        self.calls: list[dict[str, object]] = []
        self.error = error

    def stream_synthesize_result(self, text: str, *, voice_id: str, speed: float, emotion: str, cancel_event=None) -> VoiceSynthesisResult:
        del cancel_event
        self.calls.append({"text": text, "voice_id": voice_id, "speed": speed, "emotion": emotion})
        if self.error is not None:
            raise self.error
        return VoiceSynthesisResult(
            audio=text.encode("utf-8"),
            metrics=VoiceOperationMetrics(
                provider="minimax",
                request_id=f"trace-{len(self.calls)}",
                elapsed_ms=10,
                audio_duration_ms=500,
                character_count=len(text),
            ),
        )


@pytest.mark.asyncio
async def test_coordinator_emits_audio_in_sentence_order() -> None:
    service = _VoiceService()
    emitted: list[dict] = []
    coordinator = TtsTurnCoordinator(
        voice_service=service,  # type: ignore[arg-type]
        session_key="role:mira",
        request_id="turn-1",
        turn_id="voice-turn-1",
        settings=resolve_role_tts_settings({"tts": {"voice_id": "mira"}}, "平静"),
        emit_event=emitted.append,
    )

    coordinator.push("第一句。第二句")
    coordinator.finish()
    await coordinator.wait()

    assert [call["text"] for call in service.calls] == ["第一句。", "第二句"]
    assert [event["method"] for event in emitted] == [
        "voice.tts.audio",
        "voice.tts.audio",
        "voice.tts.finished",
    ]
    assert [event["payload"].get("sequence") for event in emitted] == [0, 1, None]
    assert [event["payload"]["voice_turn_id"] for event in emitted] == [
        "voice-turn-1",
        "voice-turn-1",
        "voice-turn-1",
    ]
    assert emitted[0]["payload"]["audio_base64"]
    assert emitted[0]["payload"]["metrics"] == {
        "provider": "minimax",
        "request_id": "trace-1",
        "elapsed_ms": 10,
        "audio_duration_ms": 500,
        "character_count": 4,
        "error_code": "",
    }


@pytest.mark.asyncio
async def test_tts_provider_failure_emits_diagnostic_without_raising() -> None:
    emitted: list[dict] = []
    coordinator = TtsTurnCoordinator(
        voice_service=_VoiceService(error=RuntimeError("provider down")),  # type: ignore[arg-type]
        session_key="role:mira",
        request_id="turn-2",
        turn_id="voice-turn-2",
        settings=resolve_role_tts_settings({"tts": {"voice_id": "mira"}}, "平静"),
        emit_event=emitted.append,
    )

    coordinator.push("失败。")
    coordinator.finish()
    await asyncio.wait_for(coordinator.wait(), timeout=1)

    assert [event["method"] for event in emitted] == [
        "voice.tts.error",
        "voice.tts.finished",
    ]
    assert emitted[0]["payload"]["message"] == "角色语音合成失败"
    assert emitted[0]["payload"]["metrics"] == {
        "provider": "minimax",
        "request_id": "",
        "elapsed_ms": 0,
        "audio_duration_ms": 0,
        "character_count": 3,
        "error_code": "internal_error",
    }
    assert emitted[1]["payload"] == {
        "session_key": "role:mira",
        "request_id": "turn-2",
        "voice_turn_id": "voice-turn-2",
    }


@pytest.mark.asyncio
async def test_provider_failure_stops_later_sentences_in_the_same_turn() -> None:
    emitted: list[dict] = []

    class _FailsSecondSentence(_VoiceService):
        def stream_synthesize_result(self, text: str, **kwargs) -> VoiceSynthesisResult:
            if len(self.calls) == 1:
                self.calls.append({"text": text})
                raise RuntimeError("provider down")
            return super().stream_synthesize_result(text, **kwargs)

    service = _FailsSecondSentence()
    coordinator = TtsTurnCoordinator(
        voice_service=service,  # type: ignore[arg-type]
        session_key="role:mira",
        request_id="turn-stop-after-error",
        turn_id="voice-turn-stop-after-error",
        settings=resolve_role_tts_settings({"tts": {"voice_id": "mira"}}, "平静"),
        emit_event=emitted.append,
    )

    coordinator.push("第一句。第二句。第三句。")
    coordinator.finish()
    await coordinator.wait()

    assert [call["text"] for call in service.calls] == ["第一句。", "第二句。"]
    assert [event["method"] for event in emitted] == [
        "voice.tts.audio",
        "voice.tts.error",
        "voice.tts.finished",
    ]


@pytest.mark.asyncio
async def test_tts_event_emission_failure_propagates() -> None:
    emitted: list[str] = []

    async def _fail_first_emit(event: dict[str, object]) -> None:
        emitted.append(str(event["method"]))
        if len(emitted) == 1:
            raise RuntimeError("renderer disconnected")

    coordinator = TtsTurnCoordinator(
        voice_service=_VoiceService(),  # type: ignore[arg-type]
        session_key="role:mira",
        request_id="turn-emit-failure",
        turn_id="voice-turn-emit-failure",
        settings=RoleTtsSettings(
            enabled=True,
            provider="minimax",
            voice_id="mira",
            speed=1.0,
            emotion="",
            mood="",
        ),
        emit_event=_fail_first_emit,
    )

    coordinator.push("你好。")
    coordinator.finish()

    with pytest.raises(RuntimeError, match="renderer disconnected"):
        await coordinator.wait()
    assert emitted == ["voice.tts.audio"]


@pytest.mark.asyncio
async def test_role_without_voice_id_does_not_start_provider_work() -> None:
    service = _VoiceService()
    coordinator = TtsTurnCoordinator(
        voice_service=service,  # type: ignore[arg-type]
        session_key="role:mira",
        request_id="turn-3",
        turn_id="voice-turn-3",
        settings=resolve_role_tts_settings({"tts": {}}, "平静"),
        emit_event=lambda _payload: None,
    )

    coordinator.push("不会合成。")
    coordinator.finish()
    await coordinator.wait()

    assert service.calls == []


@pytest.mark.asyncio
async def test_disabled_role_voice_does_not_start_provider_work() -> None:
    service = _VoiceService()
    coordinator = TtsTurnCoordinator(
        voice_service=service,  # type: ignore[arg-type]
        session_key="role:mira",
        request_id="turn-4",
        turn_id="voice-turn-4",
        settings=resolve_role_tts_settings({"tts": {"enabled": False, "voice_id": "mira"}}, "平静"),
        emit_event=lambda _payload: None,
    )

    coordinator.push("不会合成。")
    coordinator.finish()
    await coordinator.wait()

    assert service.calls == []


@pytest.mark.asyncio
async def test_role_provider_mismatch_does_not_start_provider_work() -> None:
    service = _VoiceService()
    coordinator = TtsTurnCoordinator(
        voice_service=service,  # type: ignore[arg-type]
        session_key="role:mira",
        request_id="turn-provider-mismatch",
        turn_id="voice-turn-provider-mismatch",
        settings=resolve_role_tts_settings(
            {"tts": {"provider": "other", "voice_id": "mira"}},
            "平静",
        ),
        emit_event=lambda _payload: None,
    )

    coordinator.push("不会合成。")
    coordinator.finish()
    await coordinator.wait()

    assert service.calls == []


@pytest.mark.asyncio
async def test_cancel_permanently_rejects_late_reply_deltas() -> None:
    service = _VoiceService()
    coordinator = TtsTurnCoordinator(
        voice_service=service,  # type: ignore[arg-type]
        session_key="role:mira",
        request_id="turn-5",
        turn_id="voice-turn-5",
        settings=resolve_role_tts_settings({"tts": {"voice_id": "mira"}}, "平静"),
        emit_event=lambda _payload: None,
    )

    coordinator.cancel()
    coordinator.push("晚到的旧回复。")
    coordinator.finish()
    await coordinator.wait()

    assert service.calls == []


@pytest.mark.asyncio
async def test_cancel_signals_in_flight_provider_stream() -> None:
    started = threading.Event()
    provider_cancelled = threading.Event()

    class _BlockingVoiceService:
        tts_provider = "minimax"

        def stream_synthesize_result(
            self,
            _text: str,
            *,
            voice_id: str,
            speed: float,
            emotion: str,
            cancel_event: threading.Event,
        ) -> VoiceSynthesisResult:
            del voice_id, speed, emotion
            started.set()
            if cancel_event.wait(timeout=1):
                provider_cancelled.set()
            raise RuntimeError("cancelled")

    coordinator = TtsTurnCoordinator(
        voice_service=_BlockingVoiceService(),  # type: ignore[arg-type]
        session_key="role:mira",
        request_id="turn-cancel-provider",
        turn_id="voice-turn-cancel-provider",
        settings=resolve_role_tts_settings({"tts": {"voice_id": "mira"}}, "平静"),
        emit_event=lambda _payload: None,
    )
    coordinator.push("正在合成。")
    assert await asyncio.to_thread(started.wait, 1)

    coordinator.cancel()
    await coordinator.wait()

    assert await asyncio.to_thread(provider_cancelled.wait, 1)
