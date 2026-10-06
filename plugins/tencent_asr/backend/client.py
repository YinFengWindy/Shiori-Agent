"""Tencent sentence recognition and TC3 signing."""

from __future__ import annotations
import base64
import hashlib
import hmac
import io
import json
import time
import urllib.parse
import uuid
import wave
from collections.abc import Callable
from datetime import datetime, timezone
from shiori_sdk.voice import (
    VoiceOperationMetrics,
    VoiceServiceError,
    VoiceTranscriptionResult,
    VoiceProviderInfo,
)
from shiori_sdk.voice_http import VoiceHttp
from .config import TencentAsrConfig

MAX_ASR_AUDIO_SECONDS = 60


def validate_wav_audio(
    audio: bytes, *, max_seconds: int = MAX_ASR_AUDIO_SECONDS
) -> None:
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

    info = VoiceProviderInfo("tencent", "腾讯语音识别")
    service = "asr"
    action = "SentenceRecognition"
    version = "2019-06-14"
    engine_type = "16k_zh"

    def __init__(
        self,
        config: TencentAsrConfig,
        http: VoiceHttp,
        *,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.config = config
        self._http = http
        self._clock = clock

    def transcribe(self, audio: bytes) -> str:
        """Returns only recognized text for compatibility with non-bridge callers."""

        return self.transcribe_result(audio).text

    def transcribe_result(self, audio: bytes) -> VoiceTranscriptionResult:
        """Returns recognized text and Tencent request diagnostics."""

        if not self.config.secret_id or not self.config.secret_key:
            raise VoiceServiceError("腾讯云 ASR 缺少 SecretId 或 SecretKey")
        validate_wav_audio(audio)
        started_at = time.perf_counter()
        timestamp = int(self._clock())
        body = {
            "EngSerViceType": self.engine_type,
            "SourceType": 1,
            "VoiceFormat": "wav",
            "Data": base64.b64encode(audio).decode("ascii"),
            "DataLen": len(audio),
        }
        payload = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode(
            "utf-8"
        )
        headers = self._signed_headers(payload, timestamp)
        try:
            response = self._http.request_json(self.config.base_url, headers, payload)
        except VoiceServiceError as exc:
            metrics = VoiceOperationMetrics(
                provider=self.info.id,
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
                provider=self.info.id,
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
                provider=self.info.id,
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
                provider=self.info.id,
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
                provider=self.info.id,
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
        canonical_headers = f"content-type:{content_type}\n" f"host:{host}\n"
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
        secret_date = hmac.new(
            b"TC3" + self.config.secret_key.encode(), date.encode(), hashlib.sha256
        ).digest()
        secret_service = hmac.new(
            secret_date, self.service.encode(), hashlib.sha256
        ).digest()
        secret_signing = hmac.new(
            secret_service, b"tc3_request", hashlib.sha256
        ).digest()
        signature = hmac.new(
            secret_signing, string_to_sign.encode(), hashlib.sha256
        ).hexdigest()
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
