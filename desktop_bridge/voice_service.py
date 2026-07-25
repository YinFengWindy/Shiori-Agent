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
from collections.abc import Callable, Iterable, Iterator
from datetime import datetime, timezone
from typing import Any

from agent.voice_config import VoiceAsrConfig, VoiceConfig, VoiceTtsConfig


class VoiceServiceError(RuntimeError):
    """Raised when a voice provider rejects a request or returns invalid data."""


JsonRequester = Callable[[str, dict[str, str], bytes], dict[str, Any]]
StreamRequester = Callable[[str, dict[str, str], bytes], Iterable[bytes]]
MultipartRequester = Callable[[str, dict[str, str], dict[str, str], str, str, bytes], dict[str, Any]]
BinaryRequester = Callable[[str], bytes]


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


def request_stream(url: str, headers: dict[str, str], body: bytes) -> Iterator[bytes]:
    """Yields provider response chunks without retaining the complete response."""

    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            for chunk in response:
                if chunk:
                    yield bytes(chunk)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise VoiceServiceError(f"语音服务 HTTP {exc.code}: {detail[:500]}") from exc
    except urllib.error.URLError as exc:
            raise VoiceServiceError(f"语音服务网络错误: {exc.reason}") from exc


def request_multipart(
    url: str,
    headers: dict[str, str],
    fields: dict[str, str],
    file_name: str,
    content_type: str,
    file_content: bytes,
) -> dict[str, Any]:
    """Uploads one transient file without persisting it in the bridge."""

    boundary = f"----ShioriVoice{uuid.uuid4().hex}"
    chunks: list[bytes] = []
    for name, value in fields.items():
        chunks.extend(
            [
                f"--{boundary}\r\n".encode(),
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(),
                str(value).encode("utf-8"),
                b"\r\n",
            ]
        )
    chunks.extend(
        [
            f"--{boundary}\r\n".encode(),
            f'Content-Disposition: form-data; name="file"; filename="{file_name}"\r\n'.encode(),
            f"Content-Type: {content_type}\r\n\r\n".encode(),
            file_content,
            b"\r\n",
            f"--{boundary}--\r\n".encode(),
        ]
    )
    request_headers = {
        **headers,
        "Content-Type": f"multipart/form-data; boundary={boundary}",
    }
    return request_json(url, request_headers, b"".join(chunks))


def request_binary(url: str) -> bytes:
    """Downloads provider-generated preview audio without writing a local file."""

    request = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        raise VoiceServiceError(f"语音试听 HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise VoiceServiceError(f"语音试听网络错误: {exc.reason}") from exc


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

    cleaned = _strip_tts_markup(text)
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


class TtsSentenceBuffer:
    """Buffers streamed reply text into bounded, spoken sentence units."""

    def __init__(self, *, max_length: int = 80) -> None:
        self._max_length = max_length
        self._buffer = ""

    def push(self, content_delta: str) -> list[str]:
        """Returns only sentences made complete by this content delta."""

        if content_delta:
            self._buffer += content_delta
        return self._drain(final=False)

    def finish(self) -> list[str]:
        """Flushes the final sentence after the assistant turn commits."""

        return self._drain(final=True)

    def _drain(self, *, final: bool) -> list[str]:
        result: list[str] = []
        while self._buffer:
            visible = _strip_unclosed_code_block(self._buffer)
            if not visible:
                break
            boundary = _find_sentence_boundary(visible)
            if boundary is None:
                normalized = _strip_tts_markup(visible)
                if len(normalized) <= self._max_length and not final:
                    break
                cut = _find_bounded_cut(visible, self._max_length)
                if cut is None:
                    if not final:
                        break
                    result.extend(split_tts_sentences(self._buffer, max_length=self._max_length))
                    self._buffer = ""
                    break
                candidate = self._buffer[:cut]
                self._buffer = self._buffer[cut:]
                result.extend(split_tts_sentences(candidate, max_length=self._max_length))
                continue

            end = boundary + 1
            candidate = self._buffer[:end]
            self._buffer = self._buffer[end:]
            result.extend(split_tts_sentences(candidate, max_length=self._max_length))
        return result


def parse_minimax_stream_chunks(chunks: Iterable[bytes]) -> Iterator[bytes]:
    """Decodes newline-delimited MiniMax JSON/``data:`` audio chunks."""

    pending = b""
    for chunk in chunks:
        pending += chunk
        while b"\n" in pending:
            line, pending = pending.split(b"\n", 1)
            yield from _parse_minimax_stream_line(line)
    if pending.strip():
        yield from _parse_minimax_stream_line(pending)


def _parse_minimax_stream_line(line: bytes) -> Iterator[bytes]:
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
    base_resp = payload.get("base_resp")
    if isinstance(base_resp, dict) and base_resp.get("status_code", 0) not in (0, None):
        raise VoiceServiceError(str(base_resp.get("status_msg") or "MiniMax TTS 请求失败"))
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


def _strip_tts_markup(text: str) -> str:
    cleaned = re.sub(r"```[\s\S]*?```", "", text)
    cleaned = re.sub(r"`([^`]*)`", r"\1", cleaned)
    cleaned = re.sub(r"!\[[^]]*\]\([^)]*\)", "", cleaned)
    cleaned = re.sub(r"\[([^]]+)\]\([^)]*\)", r"\1", cleaned)
    cleaned = re.sub(r"(^|\n)\s{0,3}#+\s*", r"\1", cleaned)
    cleaned = re.sub(r"[*_~]", "", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def _strip_unclosed_code_block(text: str) -> str:
    fences = list(re.finditer(r"```", text))
    if len(fences) % 2 == 0:
        return text
    return text[:fences[-1].start()]


def _find_sentence_boundary(text: str) -> int | None:
    fences = [match.start() for match in re.finditer(r"```", text)]
    code_ranges = list(zip(fences[0::2], fences[1::2]))
    for match in re.finditer(r"[。！？；!?;.\n]", text):
        if any(start < match.start() < end for start, end in code_ranges):
            continue
        return match.start()
    return None


def _find_bounded_cut(text: str, max_length: int) -> int | None:
    normalized = _strip_tts_markup(text)
    if len(normalized) <= max_length:
        return None
    prefix = text[:max_length]
    comma = max(prefix.rfind("，"), prefix.rfind(","))
    return (comma + 1) if comma >= 0 else max_length


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

        self._validate_request(text, voice_id, speed)
        body = self._build_body(text, voice_id=voice_id, speed=speed, emotion=emotion, stream=True)
        chunks = self._stream_requester(
            self.config.base_url,
            {"Authorization": f"Bearer {self.config.api_key}", "Content-Type": "application/json"},
            json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
        )
        audio = b"".join(parse_minimax_stream_chunks(chunks))
        if not audio:
            raise VoiceServiceError("MiniMax TTS 未返回音频")
        return audio

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
            "audio_base64": base64.b64encode(demo_audio).decode("ascii") if demo_audio else "",
            "format": "mp3",
        }

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
        if emotion:
            body["voice_setting"]["emotion"] = emotion
        return body


class VoiceService:
    """Owns configured ASR and TTS clients while keeping provider details out of IPC."""

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

    def transcribe(self, audio: bytes) -> str:
        if not self.enabled:
            raise VoiceServiceError("语音未启用")
        return self.asr.transcribe(audio)

    def synthesize(self, text: str, *, voice_id: str, speed: float, emotion: str = "") -> bytes:
        return self.tts.synthesize(text, voice_id=voice_id, speed=speed, emotion=emotion)

    def stream_synthesize(self, text: str, *, voice_id: str, speed: float, emotion: str = "") -> bytes:
        return self.tts.stream_synthesize(text, voice_id=voice_id, speed=speed, emotion=emotion)

    def clone_voice(self, audio: bytes, *, file_name: str = "voice-clone.wav") -> dict[str, Any]:
        return self.tts.clone_voice(audio, file_name=file_name)
