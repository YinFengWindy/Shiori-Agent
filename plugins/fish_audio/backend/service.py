"""Speech service validation and role voice resolution, without playback ownership."""

import base64
import binascii

from shiori_sdk.roles import Roles
from shiori_sdk.files.audio import pcm_wav_duration

from .client import FishClient, MAX_AUDIO_BYTES
from .settings import RoleVoice, VoiceStore


class SpeechService:
    """Adapt Shiori's existing TTS/ASR contracts to Fish Audio."""

    def __init__(self, store: VoiceStore, client: FishClient, roles: Roles):
        self.store, self.client, self.roles = store, client, roles

    def require_role(self, params: dict[str, object]) -> str:
        """Resolve an existing role inside the caller's role read scope."""
        role_id = params.get("role_id")
        if not isinstance(role_id, str) or self.roles.get_role(role_id) is None:
            raise ValueError("角色不存在，请先保存角色")
        return role_id

    async def synthesize(self, params: dict[str, object]) -> dict[str, object]:
        """Use the selected role's stored voice; mood is accepted without rewriting text."""
        text = params.get("text")
        if not isinstance(text, str) or not text.strip() or len(text) > 10000:
            raise ValueError("合成文本不能为空且不能超过 10000 字符")
        with self.roles.read_scope():
            role_id = self.require_role(params)
            document = self.store.read()
            voice = document.roles.get(role_id, RoleVoice())
            if not voice.reference_id:
                raise ValueError("请先在角色详情的 Fish Audio 声音卡片配置声音 ID")
        audio = await self.client.synthesize(document.settings, voice, text)
        return {
            "audio_base64": base64.b64encode(audio).decode("ascii"),
            "format": "mp3",
        }

    async def transcribe(self, params: dict[str, object]) -> dict[str, object]:
        """Reject invalid/oversized PCM recordings before uploading."""
        encoded = params.get("audio_base64")
        if params.get("format") != "wav" or not isinstance(encoded, str):
            raise ValueError("Fish Audio 语音识别需要 WAV 录音")
        if len(encoded) > ((MAX_AUDIO_BYTES + 2) // 3) * 4:
            raise ValueError("录音超过 32MB")
        try:
            audio = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error):
            raise ValueError("WAV 录音编码无效") from None
        if len(audio) > MAX_AUDIO_BYTES:
            raise ValueError("录音超过 32MB")
        _ = pcm_wav_duration(audio)
        result = await self.client.transcribe(self.store.read().settings, audio)
        return {"text": result["text"]}
