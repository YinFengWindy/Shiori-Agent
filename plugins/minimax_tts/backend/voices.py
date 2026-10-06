"""MiniMax managed voice assets and optional preview retrieval."""

from __future__ import annotations
import base64
import json
import logging
import uuid
from typing import Any
from shiori_sdk.voice import VoiceCloneResult, VoiceServiceError
from shiori_sdk.voice_http import VoiceHttp
from .preview import validate_preview_url
from .config import MiniMaxTtsConfig

logger = logging.getLogger(__name__)


class MiniMaxVoices:
    """Create and delete only explicitly managed MiniMax voice assets."""

    def __init__(self, config: MiniMaxTtsConfig, http: VoiceHttp):
        self.config = config
        self._http = http

    def clone_voice(
        self, audio: bytes, *, file_name: str = "voice-clone.wav"
    ) -> VoiceCloneResult:
        """Uploads a clone sample, creates a unique voice, and returns one preview."""

        if not self.config.api_key:
            raise VoiceServiceError("MiniMax TTS 缺少 API Key")
        if not audio:
            raise VoiceServiceError("复刻录音不能为空")
        if len(audio) > 20 * 1024 * 1024:
            raise VoiceServiceError("复刻录音不能超过 20MB")
        suffix = file_name.rsplit(".", 1)[-1].lower() if "." in file_name else "wav"
        content_type = {
            "wav": "audio/wav",
            "mp3": "audio/mpeg",
            "m4a": "audio/mp4",
        }.get(suffix)
        if content_type is None:
            raise VoiceServiceError("复刻录音必须是 WAV、MP3 或 M4A")
        headers = {"Authorization": f"Bearer {self.config.api_key}"}
        upload = self._http.request_multipart(
            self._clone_url("/v1/files/upload"),
            headers,
            {"purpose": "voice_clone"},
            file_name,
            content_type,
            audio,
        )
        self._raise_minimax_error(upload)
        file_payload = upload.get("file")
        file_id = (
            file_payload.get("file_id") if isinstance(file_payload, dict) else None
        )
        if not isinstance(file_id, int):
            raise VoiceServiceError("MiniMax 上传复刻音频未返回 file_id")
        voice_id = f"Shiori_{uuid.uuid4().hex}"
        clone = self._http.request_json(
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
        try:
            demo_audio = (
                self._http.request_binary(demo_url, validate_url=validate_preview_url)
                if demo_url
                else b""
            )
        except Exception as exc:
            logger.warning("MiniMax voice clone preview unavailable: %s", exc)
            demo_audio = b""
        return {
            "voice_id": voice_id,
            "provider": "minimax",
            "ownership": "shiori_managed",
            "audio_base64": (
                base64.b64encode(demo_audio).decode("ascii") if demo_audio else ""
            ),
            "format": "mp3",
        }

    def delete_voice(self, voice_id: str) -> None:
        """Deletes one MiniMax cloned voice previously created by Shiori."""

        if not self.config.api_key:
            raise VoiceServiceError("MiniMax TTS 缺少 API Key")
        if not voice_id.startswith("Shiori_"):
            raise VoiceServiceError("拒绝删除非 Shiori 管理的音色")
        normalized_voice_id = voice_id.strip()
        if not normalized_voice_id:
            raise VoiceServiceError("voice_id 不能为空")
        response = self._http.request_json(
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
            raise VoiceServiceError(
                str(base_resp.get("status_msg") or "MiniMax 请求失败")
            )
