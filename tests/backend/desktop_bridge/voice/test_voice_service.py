"""The host routes all speech work through active plugin contributions."""

import pytest
from agent.voice_config import VoiceAsrConfig, VoiceConfig, VoiceTtsConfig
from agent.plugin_host.effects import EffectScope
from agent.plugin_host.voice import VoiceProviderRegistry
from desktop_bridge.voice.voice_service import VoiceService
from shiori_sdk.voice import (
    VoiceCapabilities,
    VoiceProviderInfo,
    VoiceOperationMetrics,
    VoiceSynthesisResult,
    VoiceTranscriptionResult,
    VoiceServiceError,
)


class SpeechProvider:
    def __init__(self, provider_id="custom", emotions=("gentle",)):
        self.info = VoiceProviderInfo(
            provider_id,
            provider_id,
            VoiceCapabilities(emotions=emotions, voice_cloning=True),
        )
        self.calls = []

    def transcribe_result(self, audio):
        return VoiceTranscriptionResult(audio.decode(), self.metrics())

    def stream_synthesize_result(self, text, **kwargs):
        self.calls.append((text, kwargs))
        return VoiceSynthesisResult(text.encode(), self.metrics(), "mp3")

    def metrics(self):
        return VoiceOperationMetrics(self.info.id, "request", 1, 2, 3)

    def clone_voice(self, audio, *, file_name="voice-clone.wav"):
        self.calls.append((audio, file_name))
        return {
            "provider": self.info.id,
            "voice_id": "voice",
            "ownership": "shiori_managed",
            "audio_base64": "",
            "format": "mp3",
        }

    def delete_voice(self, voice_id):
        self.calls.append(voice_id)


def make_service():
    registry = VoiceProviderRegistry()
    provider = SpeechProvider()
    scope = EffectScope("custom_plugin")
    registry.register("asr", provider, scope)
    registry.register("tts", provider, scope)
    service = VoiceService(
        VoiceConfig(
            enabled=True,
            asr=VoiceAsrConfig(enabled=True, provider="custom"),
            tts=VoiceTtsConfig(enabled=True, provider="custom"),
        ),
        registry,
    )
    return service, provider, scope


def test_provider_routes_recognition_preview_replies_and_clones():
    service, provider, _ = make_service()
    assert service.transcribe(b"heard") == "heard"
    assert (
        service.synthesize("preview", voice_id="voice", speed=1, emotion="gentle")
        == b"preview"
    )
    assert (
        service.stream_synthesize_result("reply", voice_id="voice", speed=1).audio
        == b"reply"
    )
    assert service.clone_voice(b"sample")["provider"] == "custom"
    assert provider.calls[0][1]["emotion"] == "gentle"
    assert service.describe_providers()[1]["capabilities"] == {
        "emotions": ["gentle"],
        "voice_cloning": True,
    }


async def test_disabling_one_plugin_revokes_routes_without_fallback():
    service, _, scope = make_service()
    await scope.dispose_all()
    with pytest.raises(VoiceServiceError, match="ASR provider 不可用"):
        service.transcribe(b"heard")
    with pytest.raises(VoiceServiceError, match="TTS provider 不可用"):
        service.synthesize("reply", voice_id="voice", speed=1)
    assert all(not item["available"] for item in service.describe_providers())


def test_role_selection_and_asset_owner_route_independently_of_global_default():
    service, default, _ = make_service()
    other = SpeechProvider("other")
    service.providers.register("tts", other, EffectScope("other_plugin"))
    service.synthesize("role", provider="other", voice_id="other-voice", speed=1)
    service.delete_managed_voice(
        provider="other", voice_id="other-voice", ownership="shiori_managed"
    )
    assert default.calls == []
    assert other.calls[-1] == "other-voice"
    with pytest.raises(VoiceServiceError, match="外部音色"):
        service.delete_managed_voice(
            provider="other", voice_id="other-voice", ownership="external"
        )
    with pytest.raises(VoiceServiceError, match="provider 不可用"):
        service.synthesize("missing", provider="missing", voice_id="voice", speed=1)


def test_emotions_are_validated_against_selected_provider_capabilities():
    service, provider, _ = make_service()
    with pytest.raises(VoiceServiceError, match="不支持情绪"):
        service.synthesize("reply", voice_id="voice", speed=1, emotion="happy")
    assert provider.calls == []
