"""Pinned FunASR wire protocol exercised with a controlled HTTP transport."""

import httpx
import pytest
from plugins.sensevoice_asr.backend.client import SenseVoiceClient
from plugins.sensevoice_asr.backend.settings import Settings


@pytest.mark.parametrize("text", ["识别成功", ""])
async def test_explicit_model_multipart_and_empty_transcription(audio, text):
    def respond(request):
        body = request.content
        assert request.url.path == "/v1/audio/transcriptions"
        assert request.headers["content-type"].startswith("multipart/form-data;")
        assert b'name="model"\r\n\r\nsensevoice' in body
        assert b'name="response_format"\r\n\r\njson' in body
        assert audio in body
        return httpx.Response(200, json={"text": text})

    client = SenseVoiceClient(httpx.MockTransport(respond))
    try:
        assert await client.transcribe(Settings(), audio) == {"text": text}
    finally:
        await client.close()


@pytest.mark.parametrize(
    "health,error",
    [
        ({"device": "cuda", "models_loaded": ["sensevoice"], "status": "ok"}, "CPU"),
        ({"device": "cpu", "models_loaded": [], "status": "ok"}, "未加载"),
    ],
)
async def test_health_rejects_wrong_deployment(health, error):
    client = SenseVoiceClient(
        httpx.MockTransport(lambda _: httpx.Response(200, json=health))
    )
    try:
        with pytest.raises(ValueError, match=error):
            await client.health(Settings())
    finally:
        await client.close()


async def test_server_failure_is_not_retried(audio):
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(500, text="model load failed")

    client = SenseVoiceClient(httpx.MockTransport(respond))
    try:
        with pytest.raises(httpx.HTTPStatusError):
            await client.transcribe(Settings(), audio)
        assert len(calls) == 1
    finally:
        await client.close()
