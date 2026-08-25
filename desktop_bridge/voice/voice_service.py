"""Stable voice facade used by desktop bridge and callers."""

from __future__ import annotations

import threading

from agent.voice_config import VoiceConfig
from desktop_bridge.voice_models import (
    VoiceOperationMetrics,
    VoiceServiceError,
    VoiceSynthesisResult,
    VoiceTranscriptionResult,
)
from desktop_bridge.voice_providers import (
    MiniMaxTtsClient,
    TencentAsrClient,
    parse_minimax_stream_chunks,
    validate_wav_audio,
)

__all__ = [
    "MiniMaxTtsClient",
    "TencentAsrClient",
    "VoiceOperationMetrics",
    "VoiceService",
    "VoiceServiceError",
    "VoiceSynthesisResult",
    "VoiceTranscriptionResult",
    "parse_minimax_stream_chunks",
    "validate_wav_audio",
]


class VoiceService:
    """Coordinates configured provider clients without exposing IPC concerns."""

    def __init__(self, config: VoiceConfig) -> None:
        self.config = config
        self.asr = TencentAsrClient(config.asr)
        self.tts = MiniMaxTtsClient(config.tts)

    @property
    def enabled(self) -> bool:
        """Returns whether the global desktop voice switch is enabled."""

        return self.config.enabled

    @property
    def tts_enabled(self) -> bool:
        """Returns whether global voice settings allow TTS work."""

        return self.config.enabled and self.config.tts.enabled

    @property
    def tts_provider(self) -> str:
        """Returns the configured TTS provider accepted by role voice settings."""

        return self.config.tts.provider

    def transcribe(self, audio: bytes) -> str:
        if not self.enabled:
            raise VoiceServiceError("语音未启用")
        return self.asr.transcribe(audio)

    def transcribe_result(self, audio: bytes) -> VoiceTranscriptionResult:
        """Returns recognized text with structured provider diagnostics."""

        if not self.enabled:
            raise VoiceServiceError("语音未启用")
        return self.asr.transcribe_result(audio)

    def synthesize(
        self,
        text: str,
        *,
        voice_id: str,
        speed: float,
        emotion: str = "",
        cancel_event: threading.Event | None = None,
    ) -> bytes:
        if cancel_event is not None:
            return self.tts.stream_synthesize_result(
                text,
                voice_id=voice_id,
                speed=speed,
                emotion=emotion,
                cancel_event=cancel_event,
            ).audio
        return self.tts.synthesize(text, voice_id=voice_id, speed=speed, emotion=emotion)

    def stream_synthesize(self, text: str, *, voice_id: str, speed: float, emotion: str = "") -> bytes:
        return self.tts.stream_synthesize(text, voice_id=voice_id, speed=speed, emotion=emotion)

    def stream_synthesize_result(
        self,
        text: str,
        *,
        voice_id: str,
        speed: float,
        emotion: str = "",
        cancel_event: threading.Event | None = None,
    ) -> VoiceSynthesisResult:
        """Returns one synthesized sentence with structured provider diagnostics."""

        return self.tts.stream_synthesize_result(
            text,
            voice_id=voice_id,
            speed=speed,
            emotion=emotion,
            cancel_event=cancel_event,
        )

    def clone_voice(self, audio: bytes, *, file_name: str = "voice-clone.wav") -> dict[str, object]:
        return self.tts.clone_voice(audio, file_name=file_name)

    def delete_managed_voice(
        self,
        *,
        provider: str,
        voice_id: str,
        ownership: str,
    ) -> None:
        """Deletes only provider assets explicitly recorded as Shiori-managed clones."""

        if ownership != "shiori_managed":
            raise VoiceServiceError("外部音色不能由 Shiori 删除")
        if provider != self.tts_provider:
            raise VoiceServiceError("音色 provider 与当前 TTS provider 不匹配")
        if not voice_id.startswith("Shiori_"):
            raise VoiceServiceError("拒绝删除非 Shiori 管理的音色")
        self.tts.delete_voice(voice_id)
