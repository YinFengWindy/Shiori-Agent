"""A public service and file-test RPC operate without desktop-pet registration."""

import base64
import httpx
import pytest
from plugins.sensevoice_asr.backend import plugin
from plugins.sensevoice_asr.backend.client import SenseVoiceClient


async def test_service_and_independent_file_test(context, tmp_path, audio, monkeypatch):
    client = SenseVoiceClient(
        httpx.MockTransport(lambda _: httpx.Response(200, json={"text": "独立识别"}))
    )
    monkeypatch.setattr(plugin, "SenseVoiceClient", lambda: client)
    await plugin.setup(context)
    service = context.services.methods["asr", "transcribe"]
    assert await service(
        {"audio_base64": base64.b64encode(audio).decode(), "format": "wav"}
    ) == {"text": "独立识别"}
    source = tmp_path / "private_runtime/imports/sensevoice_asr-audio/clip.wav"
    source.parent.mkdir(parents=True)
    source.write_bytes(audio)
    assert await context.rpc.handlers["transcribe_file"]({"source": str(source)}) == {
        "text": "独立识别"
    }
    assert not source.exists()
    assert context.config.as_dict() == {}
    await context.aclose()
    assert not context.services.entries
    assert client.http.is_closed


async def test_malformed_audio_never_enters_http(context, monkeypatch):
    calls = []

    def unexpected_request(request):
        calls.append(request)
        return httpx.Response(500)

    client = SenseVoiceClient(httpx.MockTransport(unexpected_request))
    monkeypatch.setattr(plugin, "SenseVoiceClient", lambda: client)
    await plugin.setup(context)
    with pytest.raises(ValueError):
        await context.services.methods["asr", "transcribe"](
            {"audio_base64": "not base64", "format": "wav"}
        )
    assert calls == []
