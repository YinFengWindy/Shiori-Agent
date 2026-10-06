from shiori_sdk.testing.voice import FakeVoiceHttp
import base64
import io
import json
import wave
import pytest
from shiori_sdk.voice import VoiceServiceError
from plugins.tencent_asr.backend.client import TencentAsrClient, validate_wav_audio
from plugins.tencent_asr.backend.config import TencentAsrConfig


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
        TencentAsrConfig(secret_id="id", secret_key="key"),
        FakeVoiceHttp(requester=requester),
        clock=lambda: 1700000000,
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
        TencentAsrConfig(secret_id="id", secret_key="key"),
        FakeVoiceHttp(
            requester=lambda *_args: {
                "Response": {
                    "Error": {
                        "Code": "FailedOperation.ServiceIsolate",
                        "Message": "failed",
                    },
                    "AudioDuration": 750,
                    "RequestId": "tencent-request-error",
                }
            }
        ),
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
        TencentAsrConfig(secret_id="id", secret_key="key"),
        FakeVoiceHttp(requester=requester),
    )
    with pytest.raises(VoiceServiceError) as raised:
        client.transcribe_result(make_wav())
    assert raised.value.metrics.provider == "tencent"
    assert raised.value.metrics.request_id == ""
    assert raised.value.metrics.audio_duration_ms == 0
    assert raised.value.metrics.character_count == 0
    assert raised.value.metrics.error_code == "network_error"
    assert raised.value.metrics.elapsed_ms >= 0
