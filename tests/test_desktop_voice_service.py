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
    TtsSentenceBuffer,
    VoiceServiceError,
    parse_minimax_stream_chunks,
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


def test_tts_sentence_buffer_flushes_only_complete_sentences() -> None:
    buffer = TtsSentenceBuffer()

    assert buffer.push("你好") == []
    assert buffer.push("，今天怎么样？下一句") == ["你好，今天怎么样？"]
    assert buffer.finish() == ["下一句"]


def test_tts_sentence_buffer_drops_fenced_code_before_speaking() -> None:
    buffer = TtsSentenceBuffer()

    assert buffer.push("先说。```python\nprint('x')。\n```") == ["先说。"]
    assert buffer.push("然后说！") == ["然后说！"]
    assert buffer.finish() == []


def test_minimax_stream_parser_handles_split_sse_lines_and_hex_chunks() -> None:
    chunks = [
        b'data: {"data":{"audio":"0001"}}\n',
        b'data: {"data":{"audio":"ff"}}\n\n',
        b"data: [DONE]\n",
    ]

    assert list(parse_minimax_stream_chunks(chunks)) == [b"\x00\x01", b"\xff"]


def test_minimax_stream_synthesize_uses_streaming_request_contract() -> None:
    calls: list[dict] = []

    def stream_requester(_url: str, _headers: dict[str, str], body: bytes):
        calls.append(json.loads(body))
        return [b'data: {"data":{"audio":"0001"}}\n', b'data: {"data":{"audio":"ff"}}\n']

    client = MiniMaxTtsClient(
        VoiceTtsConfig(enabled=True, api_key="key"),
        stream_requester=stream_requester,
    )

    assert client.stream_synthesize("你好", voice_id="mira", emotion="calm") == b"\x00\x01\xff"
    assert calls[0]["stream"] is True
    assert calls[0]["audio_setting"]["format"] == "mp3"
