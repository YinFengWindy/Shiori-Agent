"""MiniMax synthesis and managed cloned voices."""

from __future__ import annotations
import json
import time
import threading
from typing import Any
from shiori_sdk.voice import (
    VoiceOperationMetrics,
    VoiceServiceError,
    VoiceSynthesisResult,
    VoiceProviderInfo,
    VoiceCapabilities,
    VoiceCloneResult,
)
from shiori_sdk.voice_http import VoiceHttp
from .voices import MiniMaxVoices
from .stream import (
    parse_minimax_stream_chunks,
    _cancelable_stream_chunks,
    _decode_audio_string,
)
from .config import MiniMaxTtsConfig

MINIMAX_AUDIO_SAMPLE_RATE = 32000
MINIMAX_AUDIO_BITRATE = 128000
MINIMAX_AUDIO_FORMAT = "mp3"
MINIMAX_AUDIO_CHANNELS = 1


class MiniMaxTtsClient:
    """Calls MiniMax HTTP TTS and returns the provider's decoded MP3 bytes."""

    info = VoiceProviderInfo(
        "minimax",
        "MiniMax 语音合成",
        VoiceCapabilities(
            emotions=(
                "happy",
                "sad",
                "angry",
                "fearful",
                "disgusted",
                "surprised",
                "calm",
                "whisper",
            ),
            voice_cloning=True,
        ),
    )

    def __init__(
        self,
        config: MiniMaxTtsConfig,
        http: VoiceHttp,
    ) -> None:
        self.config = config
        self._http = http
        self._voices = MiniMaxVoices(config, http)

    def synthesize(
        self,
        text: str,
        *,
        voice_id: str,
        speed: float = 1.0,
        emotion: str = "",
    ) -> bytes:
        self._validate_request(text, voice_id, speed)
        body = self._build_body(
            text, voice_id=voice_id, speed=speed, emotion=emotion, stream=False
        )
        payload = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode(
            "utf-8"
        )
        response = self._http.request_json(
            self.config.base_url,
            {
                "Authorization": f"Bearer {self.config.api_key}",
                "Content-Type": "application/json",
            },
            payload,
        )
        if response.get("base_resp", {}).get("status_code", 0) not in (0, None):
            message = (
                response.get("base_resp", {}).get("status_msg")
                or "MiniMax TTS 请求失败"
            )
            raise VoiceServiceError(str(message))
        raw_audio = response.get("data", {}).get("audio")
        if not isinstance(raw_audio, str) or not raw_audio:
            raise VoiceServiceError("MiniMax TTS 未返回音频")
        return _decode_audio_string(raw_audio)

    def stream_synthesize(
        self,
        text: str,
        *,
        voice_id: str,
        speed: float = 1.0,
        emotion: str = "",
    ) -> bytes:
        """Collects one sentence from MiniMax's streaming response."""

        return self.stream_synthesize_result(
            text,
            voice_id=voice_id,
            speed=speed,
            emotion=emotion,
        ).audio

    def stream_synthesize_result(
        self,
        text: str,
        *,
        voice_id: str,
        speed: float = 1.0,
        emotion: str = "",
        cancel_event: threading.Event | None = None,
    ) -> VoiceSynthesisResult:
        """Collects one sentence and its MiniMax trace diagnostics."""

        self._validate_request(text, voice_id, speed)
        if cancel_event is not None and cancel_event.is_set():
            raise VoiceServiceError("语音合成已取消", error_code="cancelled")
        started_at = time.perf_counter()
        body = self._build_body(
            text, voice_id=voice_id, speed=speed, emotion=emotion, stream=True
        )
        chunks = self._http.request_stream(
            self.config.base_url,
            {
                "Authorization": f"Bearer {self.config.api_key}",
                "Content-Type": "application/json",
            },
            json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
        )
        request_id = ""
        audio_duration_ms = 0

        def _capture_metrics(payload: dict[str, Any]) -> None:
            nonlocal request_id, audio_duration_ms
            request_id = str(payload.get("trace_id") or request_id).strip()
            extra_info = payload.get("extra_info")
            if not isinstance(extra_info, dict):
                return
            raw_duration = extra_info.get("audio_length")
            if isinstance(raw_duration, (int, float)) and raw_duration >= 0:
                audio_duration_ms = int(raw_duration)

        try:
            audio = b"".join(
                parse_minimax_stream_chunks(
                    _cancelable_stream_chunks(chunks, cancel_event),
                    on_payload=_capture_metrics,
                )
            )
        except VoiceServiceError as exc:
            metrics = VoiceOperationMetrics(
                provider=self.info.id,
                request_id=exc.request_id or request_id,
                elapsed_ms=max(0, int((time.perf_counter() - started_at) * 1000)),
                audio_duration_ms=audio_duration_ms,
                character_count=len(text),
                error_code=exc.error_code or "provider_error",
            )
            raise VoiceServiceError(
                str(exc),
                error_code=metrics.error_code,
                request_id=metrics.request_id,
                metrics=metrics,
            ) from exc
        if not audio:
            raise VoiceServiceError("MiniMax TTS 未返回音频")
        return VoiceSynthesisResult(
            audio=audio,
            metrics=VoiceOperationMetrics(
                provider=self.info.id,
                request_id=request_id,
                elapsed_ms=max(0, int((time.perf_counter() - started_at) * 1000)),
                audio_duration_ms=audio_duration_ms,
                character_count=len(text),
            ),
        )

    def clone_voice(
        self, audio: bytes, *, file_name: str = "voice-clone.wav"
    ) -> VoiceCloneResult:
        """Creates an owned voice using the provider's asset manager."""
        return self._voices.clone_voice(audio, file_name=file_name)

    def delete_voice(self, voice_id: str) -> None:
        """Deletes an owned voice through the same configured provider."""
        self._voices.delete_voice(voice_id)

    def _validate_request(self, text: str, voice_id: str, speed: float) -> None:
        if not self.config.api_key:
            raise VoiceServiceError("MiniMax TTS 缺少 API Key")
        if not text.strip() or not voice_id.strip():
            raise VoiceServiceError("text 和 voice_id 不能为空")
        if not 0.5 <= speed <= 2.0:
            raise VoiceServiceError("语速必须在 0.5 到 2.0 之间")
        if not 0.1 <= self.config.volume <= 10.0:
            raise VoiceServiceError("音量必须在 0.1 到 10.0 之间")

    def _build_body(
        self,
        text: str,
        *,
        voice_id: str,
        speed: float,
        emotion: str,
        stream: bool,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": self.config.model or "speech-2.8-turbo",
            "text": text,
            "stream": stream,
            "voice_setting": {
                "voice_id": voice_id,
                "speed": speed,
                "vol": self.config.volume,
                "pitch": 0,
            },
            "audio_setting": {
                "sample_rate": MINIMAX_AUDIO_SAMPLE_RATE,
                "bitrate": MINIMAX_AUDIO_BITRATE,
                "format": MINIMAX_AUDIO_FORMAT,
                "channel": MINIMAX_AUDIO_CHANNELS,
            },
        }
        if stream:
            body["stream_options"] = {"exclude_aggregated_audio": True}
        if emotion:
            body["voice_setting"]["emotion"] = emotion
        return body
