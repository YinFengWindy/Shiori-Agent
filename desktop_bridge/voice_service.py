from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import io
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import wave
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from agent.voice_config import VoiceAsrConfig, VoiceConfig, VoiceTtsConfig


class VoiceServiceError(RuntimeError):
    """Raised when a voice provider rejects a request or returns invalid data."""


JsonRequester = Callable[[str, dict[str, str], bytes], dict[str, Any]]


def request_json(url: str, headers: dict[str, str], body: bytes) -> dict[str, Any]:
    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise VoiceServiceError(f"语音服务 HTTP {exc.code}: {detail[:500]}") from exc
    except urllib.error.URLError as exc:
        raise VoiceServiceError(f"语音服务网络错误: {exc.reason}") from exc
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise VoiceServiceError("语音服务返回了无效 JSON") from exc
    if not isinstance(value, dict):
        raise VoiceServiceError("语音服务返回格式无效")
    return value


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
        if not self.config.enabled:
            raise VoiceServiceError("ASR 未启用")
        if self.config.provider != "tencent":
            raise VoiceServiceError(f"不支持的 ASR provider: {self.config.provider}")
        if not self.config.secret_id or not self.config.secret_key:
            raise VoiceServiceError("腾讯云 ASR 缺少 SecretId 或 SecretKey")
        validate_wav_audio(audio)
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
        response = self._requester(self.config.base_url, headers, payload)
        response_error = response.get("Response")
        if not isinstance(response_error, dict):
            raise VoiceServiceError("腾讯云 ASR 返回格式无效")
        error = response_error.get("Error")
        if isinstance(error, dict):
            raise VoiceServiceError(str(error.get("Message") or "腾讯云 ASR 请求失败"))
        result = str(response_error.get("Result") or "").strip()
        if not result:
            raise VoiceServiceError("没有听清，请重试")
        return result

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


def split_tts_sentences(text: str, *, max_length: int = 80) -> list[str]:
    """Removes non-spoken markup and creates bounded sentence-sized TTS jobs."""

    cleaned = re.sub(r"```[\s\S]*?```", "", text)
    cleaned = re.sub(r"`([^`]*)`", r"\1", cleaned)
    cleaned = re.sub(r"!\[[^]]*\]\([^)]*\)", "", cleaned)
    cleaned = re.sub(r"\[([^]]+)\]\([^)]*\)", r"\1", cleaned)
    cleaned = re.sub(r"(^|\n)\s{0,3}#+\s*", r"\1", cleaned)
    cleaned = re.sub(r"[*_~]", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if not cleaned:
        return []
    chunks = [part.strip() for part in re.split(r"(?<=[。！？；!?;])\s*|\n+", cleaned) if part.strip()]
    result: list[str] = []
    for chunk in chunks:
        while len(chunk) > max_length:
            split_at = max(
                chunk.rfind("，", 0, max_length + 1),
                chunk.rfind(",", 0, max_length + 1),
            )
            if split_at <= 0:
                split_at = max_length
            comma_at = split_at < len(chunk) and chunk[split_at] in {"，", ","}
            result.append(chunk[:split_at + (1 if comma_at else 0)].strip())
            chunk = chunk[split_at + (1 if comma_at else 0):].strip()
        if chunk:
            result.append(chunk)
    return result


class MiniMaxTtsClient:
    """Calls MiniMax HTTP TTS and returns the provider's decoded MP3 bytes."""

    def __init__(self, config: VoiceTtsConfig, *, requester: JsonRequester = request_json) -> None:
        self.config = config
        self._requester = requester

    def synthesize(
        self,
        text: str,
        *,
        voice_id: str,
        speed: float = 1.0,
        emotion: str = "",
    ) -> bytes:
        if not self.config.enabled:
            raise VoiceServiceError("TTS 未启用")
        if self.config.provider != "minimax":
            raise VoiceServiceError(f"不支持的 TTS provider: {self.config.provider}")
        if not self.config.api_key:
            raise VoiceServiceError("MiniMax TTS 缺少 API Key")
        if not voice_id.strip():
            raise VoiceServiceError("角色没有可用声音")
        if not 0.5 <= speed <= 2.0:
            raise VoiceServiceError("语速必须在 0.5 到 2.0 之间")
        body: dict[str, Any] = {
            "model": self.config.model or "speech-2.8-turbo",
            "text": text,
            "stream": False,
            "voice_setting": {"voice_id": voice_id, "speed": speed, "vol": 1, "pitch": 0},
            "audio_setting": {"sample_rate": 32000, "bitrate": 128000, "format": "mp3", "channel": 1},
        }
        if emotion:
            body["voice_setting"]["emotion"] = emotion
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
        try:
            return bytes.fromhex(raw_audio)
        except ValueError:
            try:
                return base64.b64decode(raw_audio, validate=True)
            except (binascii.Error, ValueError) as exc:
                raise VoiceServiceError("MiniMax TTS 音频数据无效") from exc


class VoiceService:
    """Owns configured ASR and TTS clients while keeping provider details out of IPC."""

    def __init__(self, config: VoiceConfig) -> None:
        self.asr = TencentAsrClient(config.asr)
        self.tts = MiniMaxTtsClient(config.tts)

    def transcribe(self, audio: bytes) -> str:
        return self.asr.transcribe(audio)

    def synthesize(self, text: str, *, voice_id: str, speed: float, emotion: str = "") -> bytes:
        return self.tts.synthesize(text, voice_id=voice_id, speed=speed, emotion=emotion)
