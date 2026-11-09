"""Public input rejection happens before any potentially billable HTTP request."""

import base64
import httpx
import pytest

from plugins.fish_audio.backend import service as service_module
from plugins.fish_audio.backend.client import FishClient
from plugins.fish_audio.backend.service import SpeechService
from plugins.fish_audio.backend.settings import VoiceStore


async def test_invalid_or_oversized_recordings_and_unconfigured_voice_do_not_upload(
    context, tmp_path, audio, monkeypatch
):
    requests = []
    client = FishClient(
        httpx.MockTransport(
            lambda request: requests.append(request) or httpx.Response(500)
        )
    )
    service = SpeechService(VoiceStore(tmp_path), client, context.fake_roles)
    try:
        for encoded in ("invalid", base64.b64encode(b"not wav").decode()):
            with pytest.raises(ValueError):
                await service.transcribe({"format": "wav", "audio_base64": encoded})
        monkeypatch.setattr(service_module, "MAX_AUDIO_BYTES", 8)
        with pytest.raises(ValueError, match="32MB"):
            await service.transcribe(
                {"format": "wav", "audio_base64": base64.b64encode(audio).decode()}
            )
        with pytest.raises(ValueError, match="声音 ID"):
            await service.synthesize({"text": "hello", "role_id": "alice", "mood": ""})
        assert requests == []
    finally:
        await client.close()
