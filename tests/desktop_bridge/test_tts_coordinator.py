from __future__ import annotations

import asyncio

import pytest

from desktop_bridge.tts_coordinator import (
    TtsTurnCoordinator,
    resolve_role_tts_settings,
)


class _VoiceService:
    def __init__(self, *, error: Exception | None = None) -> None:
        self.calls: list[dict[str, object]] = []
        self.error = error

    def stream_synthesize(self, text: str, *, voice_id: str, speed: float, emotion: str) -> bytes:
        self.calls.append({"text": text, "voice_id": voice_id, "speed": speed, "emotion": emotion})
        if self.error is not None:
            raise self.error
        return text.encode("utf-8")


def test_resolve_role_tts_settings_uses_one_mood_snapshot_and_valid_mapping() -> None:
    settings = resolve_role_tts_settings(
        {
            "tts": {
                "voice_id": "mira-voice",
                "speed": 1.4,
                "mood_tts_emotions": {"开心": "happy", "未知": "not-supported"},
            }
        },
        "开心",
    )

    assert settings.voice_id == "mira-voice"
    assert settings.speed == 1.4
    assert settings.emotion == "happy"
    assert settings.mood == "开心"
    assert resolve_role_tts_settings({"tts": {"voice_id": "voice", "speed": 9}}, "未知").speed == 1.0


@pytest.mark.asyncio
async def test_coordinator_emits_audio_in_sentence_order() -> None:
    service = _VoiceService()
    emitted: list[dict] = []
    coordinator = TtsTurnCoordinator(
        voice_service=service,  # type: ignore[arg-type]
        session_key="role:mira",
        request_id="turn-1",
        settings=resolve_role_tts_settings({"tts": {"voice_id": "mira"}}, "平静"),
        emit_event=emitted.append,
    )

    coordinator.push("第一句。第二句")
    coordinator.finish()
    await coordinator.wait()

    assert [call["text"] for call in service.calls] == ["第一句。", "第二句"]
    assert [event["method"] for event in emitted] == ["voice.tts.audio", "voice.tts.audio"]
    assert [event["payload"]["sequence"] for event in emitted] == [0, 1]
    assert emitted[0]["payload"]["audio_base64"]


@pytest.mark.asyncio
async def test_tts_provider_failure_emits_diagnostic_without_raising() -> None:
    emitted: list[dict] = []
    coordinator = TtsTurnCoordinator(
        voice_service=_VoiceService(error=RuntimeError("provider down")),  # type: ignore[arg-type]
        session_key="role:mira",
        request_id="turn-2",
        settings=resolve_role_tts_settings({"tts": {"voice_id": "mira"}}, "平静"),
        emit_event=emitted.append,
    )

    coordinator.push("失败。")
    coordinator.finish()
    await asyncio.wait_for(coordinator.wait(), timeout=1)

    assert [event["method"] for event in emitted] == ["voice.tts.error"]
    assert emitted[0]["payload"]["message"] == "角色语音合成失败"


@pytest.mark.asyncio
async def test_role_without_voice_id_does_not_start_provider_work() -> None:
    service = _VoiceService()
    coordinator = TtsTurnCoordinator(
        voice_service=service,  # type: ignore[arg-type]
        session_key="role:mira",
        request_id="turn-3",
        settings=resolve_role_tts_settings({"tts": {}}, "平静"),
        emit_event=lambda _payload: None,
    )

    coordinator.push("不会合成。")
    coordinator.finish()
    await coordinator.wait()

    assert service.calls == []
