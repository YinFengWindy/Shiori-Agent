"""Host voice selection and routing; synthesis implementations live in plugins."""

from __future__ import annotations
import threading
from typing import cast
from agent.voice_config import VoiceConfig
from agent.plugin_host.voice import VoiceProviderRegistry
from shiori_sdk.voice import (
    ManagedVoiceProvider,
    VoiceCloneResult,
    VoiceServiceError,
    VoiceSynthesisResult,
    VoiceTranscriptionResult,
)


class VoiceService:
    """Routes previews, replies, recognition and assets through the same slots."""

    def __init__(
        self, config: VoiceConfig, providers: VoiceProviderRegistry | None = None
    ) -> None:
        self.config = config
        self.providers = providers if providers is not None else VoiceProviderRegistry()

    @property
    def enabled(self) -> bool:
        """Whether the global desktop voice switch is enabled."""
        return self.config.enabled

    @property
    def tts_enabled(self) -> bool:
        """Whether host settings allow synthesis."""
        return self.config.enabled and self.config.tts.enabled

    @property
    def tts_provider(self) -> str:
        """Default provider for previews without an explicit role selection."""
        return self.config.tts.provider

    def describe_providers(self) -> list[dict[str, object]]:
        """Includes unavailable selections so settings never silently switch."""
        providers = self.providers.describe()
        for kind, selection in (
            ("asr", self.config.asr.provider),
            ("tts", self.tts_provider),
        ):
            if not any(
                item["kind"] == kind and item["id"] == selection for item in providers
            ):
                providers.append(
                    {
                        "id": selection,
                        "label": selection,
                        "kind": kind,
                        "plugin_id": "",
                        "available": False,
                        "capabilities": {"emotions": [], "voice_cloning": False},
                    }
                )
        return providers

    def transcribe(self, audio: bytes) -> str:
        """Returns recognized text for callers without metrics."""
        return self.transcribe_result(audio).text

    def transcribe_result(self, audio: bytes) -> VoiceTranscriptionResult:
        """Recognizes through the exact selected ASR contribution."""
        if not self.enabled or not self.config.asr.enabled:
            raise VoiceServiceError("ASR 未启用")
        return self.providers.asr(self.config.asr.provider).transcribe_result(audio)

    def synthesize(
        self,
        text: str,
        *,
        voice_id: str,
        speed: float,
        emotion: str = "",
        provider: str | None = None,
        cancel_event: threading.Event | None = None,
    ) -> bytes:
        """Uses the same provider path as normal role replies."""
        return self.stream_synthesize_result(
            text,
            voice_id=voice_id,
            speed=speed,
            emotion=emotion,
            provider=provider,
            cancel_event=cancel_event,
        ).audio

    def stream_synthesize_result(
        self,
        text: str,
        *,
        voice_id: str,
        speed: float,
        emotion: str = "",
        provider: str | None = None,
        cancel_event: threading.Event | None = None,
    ) -> VoiceSynthesisResult:
        """Synthesizes with provider-specific capability validation."""
        if not self.tts_enabled:
            raise VoiceServiceError("TTS 未启用")
        implementation = self.providers.tts(
            provider if provider is not None else self.tts_provider
        )
        if emotion and emotion not in implementation.info.capabilities.emotions:
            raise VoiceServiceError(
                f"{implementation.info.label} 不支持情绪: {emotion}",
                error_code="unsupported_emotion",
            )
        return implementation.stream_synthesize_result(
            text,
            voice_id=voice_id,
            speed=speed,
            emotion=emotion,
            cancel_event=cancel_event,
        )

    def clone_voice(
        self,
        audio: bytes,
        *,
        file_name: str = "voice-clone.wav",
        provider: str | None = None,
    ) -> VoiceCloneResult:
        """Creates a managed voice through the provider's optional capability."""
        if not self.tts_enabled:
            raise VoiceServiceError("TTS 未启用")
        return self._managed_provider(
            provider if provider is not None else self.tts_provider
        ).clone_voice(audio, file_name=file_name)

    def delete_managed_voice(
        self, *, provider: str, voice_id: str, ownership: str
    ) -> None:
        """Deletes via the asset's owner even when another provider is selected."""
        if ownership != "shiori_managed":
            raise VoiceServiceError("外部音色不能由 Shiori 删除")
        self._managed_provider(provider).delete_voice(voice_id)

    def _managed_provider(self, provider: str) -> ManagedVoiceProvider:
        implementation = self.providers.tts(provider)
        if not implementation.info.capabilities.voice_cloning:
            raise VoiceServiceError(
                f"TTS provider 不支持音色管理: {provider}",
                error_code="unsupported_capability",
            )
        return cast(ManagedVoiceProvider, implementation)
