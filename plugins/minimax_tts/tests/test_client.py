from shiori_sdk.testing.voice import FakeVoiceHttp
import json
import threading
import pytest
from shiori_sdk.voice import VoiceServiceError
from plugins.minimax_tts.backend.client import MiniMaxTtsClient
from plugins.minimax_tts.backend.config import MiniMaxTtsConfig


def test_minimax_tts_decodes_hex_audio_and_preserves_emotion() -> None:
    calls: list[dict] = []

    def requester(_url: str, _headers: dict[str, str], body: bytes) -> dict:
        calls.append(json.loads(body))
        return {"base_resp": {"status_code": 0}, "data": {"audio": "0001ff"}}

    client = MiniMaxTtsClient(
        MiniMaxTtsConfig(api_key="key", volume=2.5), FakeVoiceHttp(requester=requester)
    )
    assert (
        client.synthesize("你好", voice_id="mira", speed=1.2, emotion="happy")
        == b"\x00\x01\xff"
    )
    assert calls[0]["voice_setting"] == {
        "voice_id": "mira",
        "speed": 1.2,
        "vol": 2.5,
        "pitch": 0,
        "emotion": "happy",
    }
    assert calls[0]["audio_setting"] == {
        "sample_rate": 32000,
        "bitrate": 128000,
        "format": "mp3",
        "channel": 1,
    }


def test_minimax_tts_rejects_volume_outside_provider_range() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError, match="volume"):
        MiniMaxTtsConfig(api_key="key", volume=10.1)


def test_minimax_stream_synthesize_uses_streaming_request_contract() -> None:
    calls: list[dict] = []

    def stream_requester(_url: str, _headers: dict[str, str], body: bytes):
        calls.append(json.loads(body))
        return [
            b'data: {"trace_id":"minimax-trace-1","data":{"audio":"0001"}}\n',
            b'data: {"trace_id":"minimax-trace-1","data":{"audio":"ff"},"extra_info":{"audio_length":850}}\n',
        ]

    client = MiniMaxTtsClient(
        MiniMaxTtsConfig(api_key="key"),
        FakeVoiceHttp(stream_requester=stream_requester),
    )
    result = client.stream_synthesize_result("你好", voice_id="mira", emotion="calm")
    assert result.audio == b"\x00\x01\xff"
    assert result.metrics.provider == "minimax"
    assert result.metrics.request_id == "minimax-trace-1"
    assert result.metrics.audio_duration_ms == 850
    assert result.metrics.character_count == 2
    assert result.metrics.error_code == ""
    assert result.metrics.elapsed_ms >= 0
    assert calls[0]["stream"] is True
    assert calls[0]["stream_options"] == {"exclude_aggregated_audio": True}
    assert calls[0]["audio_setting"]["format"] == "mp3"


def test_minimax_stream_error_preserves_trace_and_provider_error_code() -> None:
    client = MiniMaxTtsClient(
        MiniMaxTtsConfig(api_key="key"),
        FakeVoiceHttp(
            stream_requester=lambda *_args: [
                b'data: {"trace_id":"minimax-trace-error","base_resp":{"status_code":1002,"status_msg":"rate limited"}}\n'
            ]
        ),
    )
    with pytest.raises(VoiceServiceError) as raised:
        client.stream_synthesize_result("失败", voice_id="mira")
    assert raised.value.metrics.provider == "minimax"
    assert raised.value.metrics.request_id == "minimax-trace-error"
    assert raised.value.metrics.character_count == 2
    assert raised.value.metrics.error_code == "1002"


def test_minimax_stream_cancellation_stops_before_late_audio() -> None:
    cancel_event = threading.Event()

    def chunks():
        yield b'data: {"data":{"audio":"0001"}}\n'
        cancel_event.set()
        yield b'data: {"data":{"audio":"ff"}}\n'

    client = MiniMaxTtsClient(
        MiniMaxTtsConfig(api_key="key"),
        FakeVoiceHttp(stream_requester=lambda *_args: chunks()),
    )
    with pytest.raises(VoiceServiceError) as raised:
        client.stream_synthesize_result(
            "取消", voice_id="mira", cancel_event=cancel_event
        )
    assert raised.value.metrics.error_code == "cancelled"
