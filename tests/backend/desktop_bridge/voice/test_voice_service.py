from __future__ import annotations

import base64
import io
import json
import threading
import wave
from unittest.mock import Mock

import pytest

from agent.voice_config import VoiceAsrConfig, VoiceConfig, VoiceTtsConfig
from desktop_bridge.voice.voice_service import (
    MiniMaxTtsClient,
    TencentAsrClient,
    VoiceService,
    VoiceServiceError,
    parse_minimax_stream_chunks,
    validate_wav_audio,
)


def make_wav(
    *, sample_rate: int = 16000, channels: int = 1, sample_width: int = 2
) -> bytes:
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
        return {
            "Response": {
                "Result": "你好，Mira",
                "AudioDuration": 1000,
                "RequestId": "tencent-request-1",
            }
        }

    client = TencentAsrClient(
        VoiceAsrConfig(enabled=True, secret_id="id", secret_key="key"),
        requester=requester,
        clock=lambda: 1_700_000_000,
    )

    result = client.transcribe_result(make_wav())

    assert result.text == "你好，Mira"
    assert result.metrics.provider == "tencent"
    assert result.metrics.request_id == "tencent-request-1"
    assert result.metrics.audio_duration_ms == 1000
    assert result.metrics.character_count == len("你好，Mira")
    assert result.metrics.error_code == ""
    assert result.metrics.elapsed_ms >= 0
    url, headers, body = calls[0]
    assert url == "https://asr.tencentcloudapi.com/"
    assert headers["Authorization"].startswith("TC3-HMAC-SHA256 Credential=id/")
    request = json.loads(body)
    assert request["EngSerViceType"] == "16k_zh"
    assert request["VoiceFormat"] == "wav"
    assert request["DataLen"] == len(make_wav())
    assert base64.b64decode(request["Data"]) == make_wav()


def test_tencent_asr_error_preserves_request_and_error_code() -> None:
    client = TencentAsrClient(
        VoiceAsrConfig(enabled=True, secret_id="id", secret_key="key"),
        requester=lambda *_args: {
            "Response": {
                "Error": {
                    "Code": "FailedOperation.ServiceIsolate",
                    "Message": "failed",
                },
                "AudioDuration": 750,
                "RequestId": "tencent-request-error",
            }
        },
    )

    with pytest.raises(VoiceServiceError) as raised:
        client.transcribe_result(make_wav())

    assert raised.value.metrics.provider == "tencent"
    assert raised.value.metrics.request_id == "tencent-request-error"
    assert raised.value.metrics.audio_duration_ms == 750
    assert raised.value.metrics.error_code == "FailedOperation.ServiceIsolate"


def test_tencent_asr_transport_error_records_structured_metrics() -> None:
    def requester(*_args) -> dict:
        raise VoiceServiceError("network down", error_code="network_error")

    client = TencentAsrClient(
        VoiceAsrConfig(enabled=True, secret_id="id", secret_key="key"),
        requester=requester,
    )

    with pytest.raises(VoiceServiceError) as raised:
        client.transcribe_result(make_wav())

    assert raised.value.metrics.provider == "tencent"
    assert raised.value.metrics.request_id == ""
    assert raised.value.metrics.audio_duration_ms == 0
    assert raised.value.metrics.character_count == 0
    assert raised.value.metrics.error_code == "network_error"
    assert raised.value.metrics.elapsed_ms >= 0


def test_minimax_tts_decodes_hex_audio_and_preserves_emotion() -> None:
    calls: list[dict] = []

    def requester(_url: str, _headers: dict[str, str], body: bytes) -> dict:
        calls.append(json.loads(body))
        return {"base_resp": {"status_code": 0}, "data": {"audio": "0001ff"}}

    client = MiniMaxTtsClient(
        VoiceTtsConfig(enabled=True, api_key="key", volume=2.5),
        requester=requester,
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
    client = MiniMaxTtsClient(VoiceTtsConfig(enabled=True, api_key="key", volume=10.1))

    with pytest.raises(VoiceServiceError, match="音量必须在 0.1 到 10.0 之间"):
        client.synthesize("你好", voice_id="mira")


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
        return [
            b'data: {"trace_id":"minimax-trace-1","data":{"audio":"0001"}}\n',
            b'data: {"trace_id":"minimax-trace-1","data":{"audio":"ff"},"extra_info":{"audio_length":850}}\n',
        ]

    client = MiniMaxTtsClient(
        VoiceTtsConfig(enabled=True, api_key="key"),
        stream_requester=stream_requester,
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
        VoiceTtsConfig(enabled=True, api_key="key"),
        stream_requester=lambda *_args: [
            b'data: {"trace_id":"minimax-trace-error","base_resp":{"status_code":1002,"status_msg":"rate limited"}}\n'
        ],
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
        VoiceTtsConfig(enabled=True, api_key="key"),
        stream_requester=lambda *_args: chunks(),
    )

    with pytest.raises(VoiceServiceError) as raised:
        client.stream_synthesize_result(
            "取消",
            voice_id="mira",
            cancel_event=cancel_event,
        )

    assert raised.value.metrics.error_code == "cancelled"


def test_minimax_voice_clone_uploads_transient_audio_and_returns_preview() -> None:
    uploads: list[dict[str, object]] = []
    requests: list[dict] = []

    def upload(
        url: str,
        headers: dict[str, str],
        fields: dict[str, str],
        file_name: str,
        content_type: str,
        content: bytes,
    ) -> dict:
        uploads.append(
            {
                "url": url,
                "headers": headers,
                "fields": fields,
                "file_name": file_name,
                "content_type": content_type,
                "content": content,
            }
        )
        return {"base_resp": {"status_code": 0}, "file": {"file_id": 123}}

    def requester(url: str, _headers: dict[str, str], body: bytes) -> dict:
        assert url == "https://api.minimaxi.com/v1/voice_clone"
        requests.append(json.loads(body))
        return {
            "base_resp": {"status_code": 0},
            "demo_audio": "https://demo.example/audio.mp3",
        }

    client = MiniMaxTtsClient(
        VoiceTtsConfig(enabled=True, api_key="key"),
        requester=requester,
        upload_requester=upload,
        binary_requester=lambda url: b"preview" if url.endswith("audio.mp3") else b"",
    )

    result = client.clone_voice(b"wav-bytes", file_name="sample.wav")

    assert uploads[0]["url"] == "https://api.minimaxi.com/v1/files/upload"
    assert uploads[0]["fields"] == {"purpose": "voice_clone"}
    assert uploads[0]["content_type"] == "audio/wav"
    assert requests[0]["file_id"] == 123
    assert requests[0]["voice_id"].startswith("Shiori_")
    assert result["audio_base64"] == base64.b64encode(b"preview").decode("ascii")


def test_minimax_voice_clone_keeps_voice_when_preview_download_fails() -> None:
    client = MiniMaxTtsClient(
        VoiceTtsConfig(enabled=True, api_key="key"),
        requester=lambda *_args: (
            {
                "base_resp": {"status_code": 0},
                "file": {"file_id": 123},
            }
            if _args[0].endswith("files/upload")
            else {
                "base_resp": {"status_code": 0},
                "demo_audio": "https://api.minimaxi.com/demo.mp3",
            }
        ),
        upload_requester=lambda *_args: {
            "base_resp": {"status_code": 0},
            "file": {"file_id": 123},
        },
        binary_requester=lambda _url: (_ for _ in ()).throw(
            RuntimeError("preview down")
        ),
    )

    result = client.clone_voice(b"wav-bytes")

    assert result["voice_id"].startswith("Shiori_")
    assert result["audio_base64"] == ""


def test_minimax_deletes_one_cloned_voice_by_id() -> None:
    calls: list[tuple[str, dict]] = []

    def requester(url: str, _headers: dict[str, str], body: bytes) -> dict:
        calls.append((url, json.loads(body)))
        return {"base_resp": {"status_code": 0}}

    client = MiniMaxTtsClient(
        VoiceTtsConfig(enabled=True, api_key="key"),
        requester=requester,
    )

    client.delete_voice("Shiori_voice123")

    assert calls == [
        (
            "https://api.minimaxi.com/v1/delete_voice",
            {"voice_type": "voice_cloning", "voice_id": "Shiori_voice123"},
        )
    ]


def test_voice_service_deletes_only_explicitly_managed_clones() -> None:
    service = VoiceService(
        VoiceConfig(
            enabled=True,
            tts=VoiceTtsConfig(enabled=True, provider="minimax", api_key="key"),
        )
    )
    service.tts.delete_voice = Mock()

    service.delete_managed_voice(
        provider="minimax",
        voice_id="Shiori_voice123",
        ownership="shiori_managed",
    )
    service.tts.delete_voice.assert_called_once_with("Shiori_voice123")

    with pytest.raises(VoiceServiceError, match="外部音色"):
        service.delete_managed_voice(
            provider="minimax",
            voice_id="external-voice",
            ownership="external",
        )
