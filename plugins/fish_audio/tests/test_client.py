"""Fish's actual HTTP wire and bounded failure handling, without cloud credentials."""

import asyncio
import json

import httpx
import pytest

from plugins.fish_audio.backend import client as client_module
from plugins.fish_audio.backend.client import FishClient
from plugins.fish_audio.backend.settings import RoleVoice, Settings


async def test_tts_wire_and_asr_plain_text_options(audio):
    requests = []

    def serve(request):
        requests.append(request)
        assert request.headers["authorization"] == "Bearer private-key"
        if request.url.path == "/v1/tts":
            assert request.headers["model"] == "s2.1-pro-free"
            assert json.loads(request.content) == {
                "text": "你好",
                "reference_id": "voice-alice",
                "prosody": {"speed": 1.3},
                "format": "mp3",
            }
            return httpx.Response(
                200, content=b"ID3actual-mp3", headers={"content-type": "audio/mpeg"}
            )
        assert request.url.path == "/v1/asr"
        assert request.headers["model"] == "transcribe-1-pro"
        assert request.headers["content-type"].startswith(
            "multipart/form-data; boundary="
        )
        body = request.content
        assert audio in body
        for name, value in (
            ("ignore_timestamps", "true"),
            ("diarize", "false"),
            ("tag_audio_events", "false"),
        ):
            assert f'name="{name}"\r\n\r\n{value}\r\n'.encode() in body
        return httpx.Response(200, json={"text": ""})

    client = FishClient(httpx.MockTransport(serve))
    try:
        settings = Settings(api_key="private-key")
        assert (
            await client.synthesize(
                settings, RoleVoice(reference_id="voice-alice", speed=1.3), "你好"
            )
            == b"ID3actual-mp3"
        )
        assert await client.transcribe(settings, audio) == {"text": ""}
        assert len(requests) == 2
    finally:
        await client.close()


@pytest.mark.parametrize("status", [401, 402, 429, 503, 302])
async def test_cloud_failures_do_not_retry_or_echo_private_data(status):
    calls = []

    def serve(request):
        calls.append(request)
        return httpx.Response(
            status,
            json={"message": "private-key secret speech"},
            headers={"location": "https://elsewhere.invalid"},
        )

    client = FishClient(httpx.MockTransport(serve))
    try:
        with pytest.raises(ValueError) as error:
            await client.synthesize(
                Settings(api_key="private-key"),
                RoleVoice(reference_id="voice"),
                "secret speech",
            )
        assert str(status) in str(error.value)
        assert "private-key" not in str(error.value)
        assert "secret speech" not in str(error.value)
        assert len(calls) == 1
    finally:
        await client.close()


async def test_successful_error_body_is_not_audio_and_malformed_transcript_is_not_text():
    client = FishClient(
        httpx.MockTransport(lambda _: httpx.Response(200, json={"error": "oops"}))
    )
    try:
        with pytest.raises(ValueError, match="MP3"):
            await client.synthesize(
                Settings(api_key="key"), RoleVoice(reference_id="voice"), "hello"
            )
        with pytest.raises(ValueError, match="text"):
            await client.transcribe(Settings(api_key="key"), b"audio")
    finally:
        await client.close()


async def test_response_limit_and_total_deadline_close_request(monkeypatch):
    monkeypatch.setattr(client_module, "MAX_AUDIO_BYTES", 8)
    client = FishClient(
        httpx.MockTransport(lambda _: httpx.Response(200, content=b"ID3" + b"x" * 20))
    )
    try:
        with pytest.raises(ValueError, match="大小"):
            await client.synthesize(
                Settings(api_key="key"), RoleVoice(reference_id="voice"), "hello"
            )
    finally:
        await client.close()

    async def stalled(_request):
        await asyncio.Event().wait()

    monkeypatch.setattr(client_module, "REQUEST_TIMEOUT", 0.01)
    client = FishClient(httpx.MockTransport(stalled))
    try:
        with pytest.raises(ValueError, match="超时"):
            await client.transcribe(Settings(api_key="key"), b"audio")
    finally:
        await client.close()
