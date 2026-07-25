from __future__ import annotations

import base64
import io
import json
import wave

import pytest

from agent.voice_config import VoiceAsrConfig, VoiceTtsConfig
from desktop_bridge.voice_service import (
    MiniMaxTtsClient,
    TencentAsrClient,
    VoiceServiceError,
    split_tts_sentences,
    validate_wav_audio,
)


def make_wav(*, sample_rate: int = 16000, channels: int = 1, sample_width: int = 2) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as writer:
        writer.setframerate(sample_rate)
        writer.setnchannels(channels)
        writer.setsampwidth(sample_width)
        writer.writeframes(b"\x00" * sample_width * channels * sample_rate)
    return buffer.getvalue()


def test_validate_wav_audio_requires_the_asr_contract() -> None:
    validate_wav_audio(make_wav())

    with pytest.raises(VoiceServiceError, match="16kHz"):
        validate_wav_audio(make_wav(sample_rate=8000))


def test_tencent_asr_sends_wav_and_returns_result() -> None:
    calls: list[tuple[str, dict[str, str], bytes]] = []

    def requester(url: str, headers: dict[str, str], body: bytes) -> dict:
        calls.append((url, headers, body))
        return {"Response": {"Result": "你好，Mira"}}

    client = TencentAsrClient(
        VoiceAsrConfig(enabled=True, secret_id="id", secret_key="key"),
        requester=requester,
        clock=lambda: 1_700_000_000,
    )

    assert client.transcribe(make_wav()) == "你好，Mira"
    url, headers, body = calls[0]
    assert url == "https://asr.tencentcloudapi.com/"
    assert headers["Authorization"].startswith("TC3-HMAC-SHA256 Credential=id/")
    request = json.loads(body)
    assert request["VoiceFormat"] == "wav"
    assert request["DataLen"] == len(make_wav())
    assert base64.b64decode(request["Data"]) == make_wav()


def test_minimax_tts_decodes_hex_audio_and_preserves_emotion() -> None:
    calls: list[dict] = []

    def requester(_url: str, _headers: dict[str, str], body: bytes) -> dict:
        calls.append(json.loads(body))
        return {"base_resp": {"status_code": 0}, "data": {"audio": "0001ff"}}

    client = MiniMaxTtsClient(
        VoiceTtsConfig(enabled=True, api_key="key"),
        requester=requester,
    )

    assert client.synthesize("你好", voice_id="mira", speed=1.2, emotion="happy") == b"\x00\x01\xff"
    assert calls[0]["voice_setting"] == {
        "voice_id": "mira",
        "speed": 1.2,
        "vol": 1,
        "pitch": 0,
        "emotion": "happy",
    }
    assert calls[0]["audio_setting"] == {
        "sample_rate": 32000,
        "bitrate": 128000,
        "format": "mp3",
        "channel": 1,
    }


def test_split_tts_sentences_removes_markdown_and_limits_chunks() -> None:
    sentences = split_tts_sentences("# 标题\n你好。`代码`，" + "很长" * 50 + "！")

    assert sentences[0] == "标题 你好。"
    assert sentences[1].startswith("代码，")
    assert all(len(sentence) <= 80 for sentence in sentences)
