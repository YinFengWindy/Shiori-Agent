from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import io
import json
import time
import threading
import urllib.parse
import uuid
import wave
from collections.abc import Callable, Iterable, Iterator
from datetime import datetime, timezone
from typing import Any

from agent.voice_config import VoiceAsrConfig, VoiceTtsConfig
from desktop_bridge.voice_http import (
    BinaryRequester,
    JsonRequester,
    MultipartRequester,
    StreamRequester,
    request_binary,
    request_json,
    request_multipart,
    request_stream,
)
from desktop_bridge.voice_models import (
    VoiceOperationMetrics,
    VoiceServiceError,
    VoiceSynthesisResult,
    VoiceTranscriptionResult,
)


def validate_wav_audio(audio: bytes, *, max_seconds: int = 60) -> None:
    """Validates the fixed 16 kHz mono PCM contract used by cloud ASR."""

    try:
        with wave.open(io.BytesIO(audio), "rb") as reader:
            channels = reader.getnchannels()
            sample_width = reader.getsampwidth()
            sample_rate = reader.getframerate()
            frame_count = reader.getnframes()
    except (EOFError, wave.Error) as exc:
        raise VoiceServiceError("录音不是有效的 WAV 文件") from exc
    if (channels, sample_width, sample_rate) != (1, 2, 16000):
        raise VoiceServiceError("录音必须是 16kHz、单声道、16-bit PCM WAV")
    if frame_count <= 0:
        raise VoiceServiceError("录音内容为空")
    if frame_count > 16000 * max_seconds:
        raise VoiceServiceError(f"录音不能超过 {max_seconds} 秒")


class TencentAsrClient:
    """Calls Tencent Cloud's one-sentence recognition API with TC3 signing."""

    service = "asr"
    action = "SentenceRecognition"
    version = "2019-06-14"

    def __init__(
        self,
        config: VoiceAsrConfig,
        *,
        requester: JsonRequester = request_json,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.config = config
        self._requester = requester
        self._clock = clock

    def transcribe(self, audio: bytes) -> str:
        """Returns only recognized text for compatibility with non-bridge callers."""

        return self.transcribe_result(audio).text

    def transcribe_result(self, audio: bytes) -> VoiceTranscriptionResult:
        """Returns recognized text and Tencent request diagnostics."""

        if not self.config.enabled:
            raise VoiceServiceError("ASR 未启用")
        if self.config.provider != "tencent":
            raise VoiceServiceError(f"不支持的 ASR provider: {self.config.provider}")
        if not self.config.secret_id or not self.config.secret_key:
            raise VoiceServiceError("腾讯云 ASR 缺少 SecretId 或 SecretKey")
        validate_wav_audio(audio)
        started_at = time.perf_counter()
        timestamp = int(self._clock())
        body = {
            "EngSerViceType": self.config.model or "16k_zh",
            "SourceType": 1,
            "VoiceFormat": "wav",
            "Data": base64.b64encode(audio).decode("ascii"),
            "DataLen": len(audio),
        }
        payload = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        headers = self._signed_headers(payload, timestamp)
        try:
            response = self._requester(self.config.base_url, headers, payload)
        except VoiceServiceError as exc:
            metrics = VoiceOperationMetrics(
                provider=self.config.provider,
                request_id=exc.request_id,
                elapsed_ms=max(0, int((time.perf_counter() - started_at) * 1000)),
                audio_duration_ms=0,
                character_count=0,
                error_code=exc.error_code or "transport_error",
            )
            raise VoiceServiceError(
                str(exc),
                error_code=metrics.error_code,
                request_id=metrics.request_id,
                metrics=metrics,
            ) from exc
        response_error = response.get("Response")
        if not isinstance(response_error, dict):
            metrics = VoiceOperationMetrics(
                provider=self.config.provider,
                request_id="",
                elapsed_ms=max(0, int((time.perf_counter() - started_at) * 1000)),
                audio_duration_ms=0,
                character_count=0,
                error_code="invalid_response",
            )
            raise VoiceServiceError(
                "腾讯云 ASR 返回格式无效",
                error_code=metrics.error_code,
                metrics=metrics,
            )
        raw_audio_duration_ms = response_error.get("AudioDuration")
        audio_duration_ms = (
            int(raw_audio_duration_ms)
            if isinstance(raw_audio_duration_ms, (int, float))
            and raw_audio_duration_ms >= 0
            else 0
        )
        request_id = str(response_error.get("RequestId") or "").strip()
        error = response_error.get("Error")
        if isinstance(error, dict):
            error_code = str(error.get("Code") or "provider_error").strip()
            metrics = VoiceOperationMetrics(
                provider=self.config.provider,
                request_id=request_id,
                elapsed_ms=max(0, int((time.perf_counter() - started_at) * 1000)),
                audio_duration_ms=audio_duration_ms,
                character_count=0,
                error_code=error_code,
            )
            raise VoiceServiceError(
                str(error.get("Message") or "腾讯云 ASR 请求失败"),
                error_code=error_code,
                request_id=request_id,
                metrics=metrics,
            )
        result = str(response_error.get("Result") or "").strip()
        if not result:
            metrics = VoiceOperationMetrics(
                provider=self.config.provider,
                request_id=request_id,
                elapsed_ms=max(0, int((time.perf_counter() - started_at) * 1000)),
                audio_duration_ms=audio_duration_ms,
                character_count=0,
                error_code="no_speech",
            )
            raise VoiceServiceError(
                "没有听清，请重试",
                error_code=metrics.error_code,
                request_id=request_id,
                metrics=metrics,
            )
        return VoiceTranscriptionResult(
            text=result,
            metrics=VoiceOperationMetrics(
                provider=self.config.provider,
                request_id=request_id,
                elapsed_ms=max(0, int((time.perf_counter() - started_at) * 1000)),
                audio_duration_ms=audio_duration_ms,
                character_count=len(result),
            ),
        )

    def _signed_headers(self, payload: bytes, timestamp: int) -> dict[str, str]:
        url = self.config.base_url
        host = urllib.parse.urlparse(url).netloc or "asr.tencentcloudapi.com"
        date = datetime.fromtimestamp(timestamp, tz=timezone.utc).strftime("%Y-%m-%d")
        content_type = "application/json; charset=utf-8"
        canonical_headers = (
            f"content-type:{content_type}\n"
            f"host:{host}\n"
        )
        signed_headers = "content-type;host"
        hashed_payload = hashlib.sha256(payload).hexdigest()
        canonical_request = "\n".join(
            ["POST", "/", "", canonical_headers, signed_headers, hashed_payload]
        )
        credential_scope = f"{date}/{self.service}/tc3_request"
        string_to_sign = "\n".join(
            [
                "TC3-HMAC-SHA256",
                str(timestamp),
                credential_scope,
                hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
            ]
        )
        secret_date = hmac.new(b"TC3" + self.config.secret_key.encode(), date.encode(), hashlib.sha256).digest()
        secret_service = hmac.new(secret_date, self.service.encode(), hashlib.sha256).digest()
        secret_signing = hmac.new(secret_service, b"tc3_request", hashlib.sha256).digest()
        signature = hmac.new(secret_signing, string_to_sign.encode(), hashlib.sha256).hexdigest()
        authorization = (
            f"TC3-HMAC-SHA256 Credential={self.config.secret_id}/{credential_scope}, "
            f"SignedHeaders={signed_headers}, Signature={signature}"
        )
        return {
            "Authorization": authorization,
            "Content-Type": content_type,
            "Host": host,
            "X-TC-Action": self.action,
            "X-TC-Version": self.version,
            "X-TC-Timestamp": str(timestamp),
            "X-TC-Nonce": str(uuid.uuid4().int % 2**31),
        }


def parse_minimax_stream_chunks(
    chunks: Iterable[bytes],
    *,
    on_payload: Callable[[dict[str, Any]], None] | None = None,
) -> Iterator[bytes]:
    """Decodes newline-delimited MiniMax JSON/``data:`` audio chunks."""

    pending = b""
    for chunk in chunks:
        pending += chunk
        while b"\n" in pending:
            line, pending = pending.split(b"\n", 1)
            yield from _parse_minimax_stream_line(line, on_payload=on_payload)
    if pending.strip():
        yield from _parse_minimax_stream_line(pending, on_payload=on_payload)


def _cancelable_stream_chunks(
    chunks: Iterable[bytes],
    cancel_event: threading.Event | None,
) -> Iterator[bytes]:
    for chunk in chunks:
        if cancel_event is not None and cancel_event.is_set():
            raise VoiceServiceError("语音合成已取消", error_code="cancelled")
        yield chunk
    if cancel_event is not None and cancel_event.is_set():
        raise VoiceServiceError("语音合成已取消", error_code="cancelled")


def _parse_minimax_stream_line(
    line: bytes,
    *,
    on_payload: Callable[[dict[str, Any]], None] | None = None,
) -> Iterator[bytes]:
    text = line.decode("utf-8", errors="replace").strip()
    if not text or text == "[DONE]":
        return
    if text.startswith("data:"):
        text = text[5:].strip()
    if text == "[DONE]":
        return
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise VoiceServiceError("MiniMax TTS 流式响应格式无效") from exc
    if not isinstance(payload, dict):
        raise VoiceServiceError("MiniMax TTS 流式响应格式无效")
    if on_payload is not None:
        on_payload(payload)
    base_resp = payload.get("base_resp")
    if isinstance(base_resp, dict) and base_resp.get("status_code", 0) not in (0, None):
        raise VoiceServiceError(
            str(base_resp.get("status_msg") or "MiniMax TTS 请求失败"),
            error_code=str(base_resp.get("status_code") or ""),
            request_id=str(payload.get("trace_id") or "").strip(),
        )
    data = payload.get("data")
    if not isinstance(data, dict):
        return
    raw_audio = data.get("audio")
    if not isinstance(raw_audio, str) or not raw_audio:
        return
    yield _decode_audio_string(raw_audio)


def _decode_audio_string(raw_audio: str) -> bytes:
    try:
        return bytes.fromhex(raw_audio)
    except ValueError:
        try:
            return base64.b64decode(raw_audio, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise VoiceServiceError("MiniMax TTS 音频数据无效") from exc


class MiniMaxTtsClient:
    """Calls MiniMax HTTP TTS and returns the provider's decoded MP3 bytes."""

    def __init__(
        self,
        config: VoiceTtsConfig,
        *,
        requester: JsonRequester = request_json,
        stream_requester: StreamRequester = request_stream,
        upload_requester: MultipartRequester = request_multipart,
        binary_requester: BinaryRequester = request_binary,
    ) -> None:
        self.config = config
        self._requester = requester
        self._stream_requester = stream_requester
        self._upload_requester = upload_requester
        self._binary_requester = binary_requester

    def synthesize(
        self,
        text: str,
        *,
        voice_id: str,
        speed: float = 1.0,
        emotion: str = "",
    ) -> bytes:
        self._validate_request(text, voice_id, speed)
        body = self._build_body(text, voice_id=voice_id, speed=speed, emotion=emotion, stream=False)
        payload = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        response = self._requester(
            self.config.base_url,
            {"Authorization": f"Bearer {self.config.api_key}", "Content-Type": "application/json"},
            payload,
        )
        if response.get("base_resp", {}).get("status_code", 0) not in (0, None):
            message = response.get("base_resp", {}).get("status_msg") or "MiniMax TTS 请求失败"
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
        body = self._build_body(text, voice_id=voice_id, speed=speed, emotion=emotion, stream=True)
        chunks = self._stream_requester(
            self.config.base_url,
            {"Authorization": f"Bearer {self.config.api_key}", "Content-Type": "application/json"},
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
                provider=self.config.provider,
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
                provider=self.config.provider,
                request_id=request_id,
                elapsed_ms=max(0, int((time.perf_counter() - started_at) * 1000)),
                audio_duration_ms=audio_duration_ms,
                character_count=len(text),
            ),
        )

    def clone_voice(self, audio: bytes, *, file_name: str = "voice-clone.wav") -> dict[str, Any]:
        """Uploads a clone sample, creates a unique voice, and returns one preview."""

        if not self.config.enabled:
            raise VoiceServiceError("TTS 未启用")
        if self.config.provider != "minimax":
            raise VoiceServiceError(f"不支持的 TTS provider: {self.config.provider}")
        if not self.config.api_key:
            raise VoiceServiceError("MiniMax TTS 缺少 API Key")
        if not audio:
            raise VoiceServiceError("复刻录音不能为空")
        if len(audio) > 20 * 1024 * 1024:
            raise VoiceServiceError("复刻录音不能超过 20MB")
        suffix = file_name.rsplit(".", 1)[-1].lower() if "." in file_name else "wav"
        content_type = {"wav": "audio/wav", "mp3": "audio/mpeg", "m4a": "audio/mp4"}.get(suffix)
        if content_type is None:
            raise VoiceServiceError("复刻录音必须是 WAV、MP3 或 M4A")
        headers = {"Authorization": f"Bearer {self.config.api_key}"}
        upload = self._upload_requester(
            self._clone_url("/v1/files/upload"),
            headers,
            {"purpose": "voice_clone"},
            file_name,
            content_type,
            audio,
        )
        self._raise_minimax_error(upload)
        file_payload = upload.get("file")
        file_id = file_payload.get("file_id") if isinstance(file_payload, dict) else None
        if not isinstance(file_id, int):
            raise VoiceServiceError("MiniMax 上传复刻音频未返回 file_id")
        voice_id = f"Shiori_{uuid.uuid4().hex}"
        clone = self._requester(
            self._clone_url("/v1/voice_clone"),
            {**headers, "Content-Type": "application/json"},
            json.dumps(
                {
                    "file_id": file_id,
                    "voice_id": voice_id,
                    "text": "你好，这是我的声音。",
                    "model": self.config.model or "speech-2.8-turbo",
                },
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8"),
        )
        self._raise_minimax_error(clone)
        demo_url = str(clone.get("demo_audio") or "").strip()
        demo_audio = self._binary_requester(demo_url) if demo_url else b""
        return {
            "voice_id": voice_id,
            "provider": self.config.provider,
            "ownership": "shiori_managed",
            "audio_base64": base64.b64encode(demo_audio).decode("ascii") if demo_audio else "",
            "format": "mp3",
        }

    def delete_voice(self, voice_id: str) -> None:
        """Deletes one MiniMax cloned voice previously created by Shiori."""

        if not self.config.enabled:
            raise VoiceServiceError("TTS 未启用")
        if self.config.provider != "minimax":
            raise VoiceServiceError(f"不支持的 TTS provider: {self.config.provider}")
        if not self.config.api_key:
            raise VoiceServiceError("MiniMax TTS 缺少 API Key")
        normalized_voice_id = voice_id.strip()
        if not normalized_voice_id:
            raise VoiceServiceError("voice_id 不能为空")
        response = self._requester(
            self._clone_url("/v1/delete_voice"),
            {
                "Authorization": f"Bearer {self.config.api_key}",
                "Content-Type": "application/json",
            },
            json.dumps(
                {
                    "voice_type": "voice_cloning",
                    "voice_id": normalized_voice_id,
                },
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8"),
        )
        self._raise_minimax_error(response)

    def _clone_url(self, path: str) -> str:
        base = self.config.base_url.rstrip("/")
        for suffix in ("/v1/t2a_v2", "/v1"):
            if base.endswith(suffix):
                base = base[: -len(suffix)]
                break
        return f"{base}{path}"

    @staticmethod
    def _raise_minimax_error(response: dict[str, Any]) -> None:
        base_resp = response.get("base_resp")
        if not isinstance(base_resp, dict):
            raise VoiceServiceError("MiniMax 返回格式无效")
        if base_resp.get("status_code", 0) not in (0, None):
            raise VoiceServiceError(str(base_resp.get("status_msg") or "MiniMax 请求失败"))

    def _validate_request(self, text: str, voice_id: str, speed: float) -> None:
        if not self.config.enabled:
            raise VoiceServiceError("TTS 未启用")
        if self.config.provider != "minimax":
            raise VoiceServiceError(f"不支持的 TTS provider: {self.config.provider}")
        if not self.config.api_key:
            raise VoiceServiceError("MiniMax TTS 缺少 API Key")
        if not text.strip() or not voice_id.strip():
            raise VoiceServiceError("text 和 voice_id 不能为空")
        if not 0.5 <= speed <= 2.0:
            raise VoiceServiceError("语速必须在 0.5 到 2.0 之间")

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
            "voice_setting": {"voice_id": voice_id, "speed": speed, "vol": 1, "pitch": 0},
            "audio_setting": {"sample_rate": 32000, "bitrate": 128000, "format": "mp3", "channel": 1},
        }
        if stream:
            body["stream_options"] = {"exclude_aggregated_audio": True}
        if emotion:
            body["voice_setting"]["emotion"] = emotion
        return body
