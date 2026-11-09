"""File-test uploads are confined to the plugin's staged files and always cleaned."""

import httpx
import pytest

from plugins.fish_audio.backend import plugin
from plugins.fish_audio.backend.client import FishClient
from plugins.fish_audio.backend.settings import VoiceStore


async def test_staged_file_cleanup_on_success_and_failure_and_path_isolation(
    context, tmp_path, audio, monkeypatch
):
    fail = False

    def serve(_request):
        return (
            httpx.Response(402)
            if fail
            else httpx.Response(200, json={"text": "识别成功"})
        )

    client = FishClient(httpx.MockTransport(serve))
    monkeypatch.setattr(plugin, "FishClient", lambda: client)
    VoiceStore(tmp_path).save_settings({"api_key": "key", "tts_model": "s2-pro"})
    await plugin.setup(context)
    handler = context.fake_rpc.handlers["transcribe_file"]
    source = tmp_path / "private_runtime/imports/fish_audio-audio/clip.wav"
    source.parent.mkdir(parents=True)
    source.write_bytes(audio)
    assert await handler({"source": str(source)}) == {"text": "识别成功"}
    assert not source.exists()
    fail = True
    source.write_bytes(audio)
    with pytest.raises(ValueError, match="额度"):
        await handler({"source": str(source)})
    assert not source.exists()
    outside = tmp_path / "other.wav"
    outside.write_bytes(audio)
    with pytest.raises(ValueError):
        await handler({"source": str(outside)})
    assert outside.read_bytes() == audio
