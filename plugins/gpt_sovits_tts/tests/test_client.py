"""Official v2ProPlus API requests and error/silence handling."""

import json

import httpx
import pytest
from plugins.gpt_sovits_tts.backend.client import SovitsClient
from plugins.gpt_sovits_tts.backend.settings import Settings


async def test_weights_then_complete_wav(wav_bytes):
    requests = []
    payload = {
        "text": "你好",
        "text_lang": "auto",
        "ref_audio_path": "C:/private/reference.wav",
        "prompt_lang": "zh",
        "prompt_text": "参考",
        "speed_factor": 1.2,
        "media_type": "wav",
        "streaming_mode": False,
    }

    def respond(request):
        requests.append(request)
        if request.url.path != "/tts":
            return httpx.Response(200, json={"message": "success"})
        assert json.loads(request.content) == payload
        assert request.extensions["timeout"]["read"] is None
        return httpx.Response(200, content=wav_bytes(1))

    client = SovitsClient(httpx.MockTransport(respond))
    try:
        assert await client.synthesize(Settings(), payload) == wav_bytes(1)
        assert [request.url.path for request in requests] == [
            "/set_gpt_weights",
            "/set_sovits_weights",
            "/tts",
        ]
        assert requests[1].url.params["weights_path"].endswith("s2Gv2ProPlus.pth")
    finally:
        await client.close()


@pytest.mark.parametrize(
    "status,body",
    [
        (400, b'{"message":"reference invalid"}'),
        (500, b"model failed"),
        (200, b"invalid audio"),
    ],
)
async def test_explicit_and_non_json_errors_do_not_become_audio(status, body):
    client = SovitsClient(
        httpx.MockTransport(
            lambda request: (
                httpx.Response(status, content=body)
                if request.url.path == "/tts"
                else httpx.Response(200, json={"message": "success"})
            )
        )
    )
    try:
        with pytest.raises(ValueError):
            await client.synthesize(Settings(), {})
    finally:
        await client.close()


async def test_200_silence_is_rejected(wav_bytes):
    client = SovitsClient(
        httpx.MockTransport(
            lambda request: (
                httpx.Response(200, content=wav_bytes(1, 0))
                if request.url.path == "/tts"
                else httpx.Response(200, json={"message": "success"})
            )
        )
    )
    try:
        with pytest.raises(ValueError, match="静音"):
            await client.synthesize(Settings(), {})
    finally:
        await client.close()


async def test_health_does_not_claim_acoustic_model_verification():
    client = SovitsClient(
        httpx.MockTransport(
            lambda _: httpx.Response(
                200,
                json={
                    "paths": {
                        "/tts": {},
                        "/set_gpt_weights": {},
                        "/set_sovits_weights": {},
                    }
                },
            )
        )
    )
    try:
        result = await client.health(Settings())
        assert result["reachable"] is True
        assert result["model_verified"] is False
    finally:
        await client.close()
