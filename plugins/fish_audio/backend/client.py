"""Explicit Fish REST protocols with bounded responses and no automatic retries."""

import asyncio
import json

import httpx

from .settings import RoleVoice, Settings

API_URL = "https://api.fish.audio"
MAX_AUDIO_BYTES = 32 * 1024 * 1024
MAX_TRANSCRIPT_BYTES = 1024 * 1024
REQUEST_TIMEOUT = 90.0


class FishClient:
    """Own a cloud connection pool for both providers."""

    def __init__(self, transport: httpx.AsyncBaseTransport | None = None):
        self.http = httpx.AsyncClient(
            transport=transport,
            follow_redirects=False,
            timeout=httpx.Timeout(60, connect=10),
        )

    async def close(self) -> None:
        """Release connections when this plugin generation unloads."""
        await self.http.aclose()

    async def _request(
        self,
        path: str,
        settings: Settings,
        model: str,
        limit: int,
        *,
        json_body: dict[str, object] | None = None,
        files: dict[str, tuple[str, bytes, str]] | None = None,
        data: dict[str, str] | None = None,
    ) -> tuple[bytes, str]:
        if not settings.api_key:
            raise ValueError("请先在 Fish Audio 插件设置中配置 API Key")
        try:
            async with asyncio.timeout(REQUEST_TIMEOUT):
                async with self.http.stream(
                    "POST",
                    API_URL + path,
                    headers={
                        "Authorization": f"Bearer {settings.api_key}",
                        "model": model,
                    },
                    json=json_body,
                    files=files,
                    data=data,
                ) as response:
                    if response.status_code != 200:
                        messages = {
                            400: "请求参数或声音 ID 无效",
                            401: "API Key 无效",
                            403: "没有访问权限",
                            402: "账户额度不足",
                            404: "声音或服务不存在",
                            429: "请求过于频繁，请稍后重试",
                        }
                        reason = messages.get(response.status_code, "云端服务请求失败")
                        # Never surface upstream bodies, which can echo private input or keys.
                        raise ValueError(
                            f"Fish Audio HTTP {response.status_code}：{reason}"
                        )
                    chunks = bytearray()
                    async for chunk in response.aiter_bytes():
                        if len(chunks) + len(chunk) > limit:
                            raise ValueError("Fish Audio 响应超过大小限制")
                        chunks.extend(chunk)
                    return (
                        bytes(chunks),
                        response.headers.get("content-type", "").split(";")[0].lower(),
                    )
        except (TimeoutError, httpx.TimeoutException):
            raise ValueError("Fish Audio 请求超时，请重试") from None
        except httpx.RequestError:
            raise ValueError("无法连接 Fish Audio，请检查网络") from None

    async def synthesize(
        self, settings: Settings, voice: RoleVoice, text: str
    ) -> bytes:
        """Return a complete MP3, refusing error bodies disguised as success."""
        audio, content_type = await self._request(
            "/v1/tts",
            settings,
            settings.tts_model,
            MAX_AUDIO_BYTES,
            json_body={
                "text": text,
                "reference_id": voice.reference_id,
                "prosody": {"speed": voice.speed},
                "format": "mp3",
            },
        )
        # MP3 starts with ID3 metadata or an MPEG audio frame header.
        mp3 = audio.startswith(b"ID3") or (
            len(audio) >= 4 and audio[0] == 0xFF and audio[1] & 0xE0 == 0xE0
        )
        if not mp3 or content_type in {"application/json", "text/html", "text/plain"}:
            raise ValueError("Fish Audio 未返回有效 MP3 音频")
        return audio

    async def transcribe(self, settings: Settings, audio: bytes) -> dict[str, str]:
        """Request plain transcription without speaker, emotion or timestamp annotations."""
        content, _ = await self._request(
            "/v1/asr",
            settings,
            "transcribe-1-pro",
            MAX_TRANSCRIPT_BYTES,
            files={"audio": ("audio.wav", audio, "audio/wav")},
            data={
                "ignore_timestamps": "true",
                "diarize": "false",
                "tag_audio_events": "false",
            },
        )
        try:
            result: dict[str, object] = json.loads(content)
        except (ValueError, UnicodeError):
            raise ValueError("Fish Audio 转写响应格式无效") from None
        if not isinstance(result, dict):
            raise ValueError("Fish Audio 转写响应格式无效")
        text = result.get("text")
        if not isinstance(text, str):
            raise ValueError("Fish Audio 转写响应缺少 text")
        return {"text": text}
