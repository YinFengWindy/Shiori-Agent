"""Typed ASR/TTS contributions; capture, playback and selection remain host-owned."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Protocol, TypedDict

from .voice_http import VoiceHttp
from .extensions import ConfigValues
from .runtime import PluginRuntimeContext


class VoiceServiceError(RuntimeError):
    """A provider operation failed with optional non-sensitive diagnostics."""

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "",
        request_id: str = "",
        metrics: VoiceOperationMetrics | None = None,
    ) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.request_id = request_id
        self.metrics = metrics


@dataclass(frozen=True)
class VoiceOperationMetrics:
    """Non-sensitive diagnostics for one recognition or synthesis operation."""

    provider: str
    request_id: str
    elapsed_ms: int
    audio_duration_ms: int
    character_count: int
    error_code: str = ""

    def to_dict(self) -> dict[str, str | int]:
        """Serializes diagnostics for bridge events and message metadata."""
        return {
            "provider": self.provider,
            "request_id": self.request_id,
            "elapsed_ms": self.elapsed_ms,
            "audio_duration_ms": self.audio_duration_ms,
            "character_count": self.character_count,
            "error_code": self.error_code,
        }


@dataclass(frozen=True)
class VoiceTranscriptionResult:
    """Recognized text and diagnostics from one recorded PCM WAV segment."""

    text: str
    metrics: VoiceOperationMetrics


@dataclass(frozen=True)
class VoiceSynthesisResult:
    """Complete encoded audio for a sentence; format names the actual codec."""

    audio: bytes
    metrics: VoiceOperationMetrics
    format: str = "mp3"


@dataclass(frozen=True)
class VoiceCapabilities:
    """Capabilities a provider actually implements, used for settings and validation."""

    emotions: tuple[str, ...] = ()
    voice_cloning: bool = False


@dataclass(frozen=True)
class VoiceProviderInfo:
    """Stable identity and display name independent of the owning plugin ID."""

    id: str
    label: str
    capabilities: VoiceCapabilities = VoiceCapabilities()


class VoiceCloneResult(TypedDict):
    """A newly managed voice plus optional encoded preview returned by its provider."""

    provider: str
    voice_id: str
    ownership: str
    audio_base64: str
    format: str


class AsrProvider(Protocol):
    """Blocking recognition runs on the host worker, never the UI event loop."""

    @property
    def info(self) -> VoiceProviderInfo: ...
    def transcribe_result(self, audio: bytes) -> VoiceTranscriptionResult: ...


class TtsProvider(Protocol):
    """One synthesis path is shared by role replies and manual previews."""

    @property
    def info(self) -> VoiceProviderInfo: ...
    def stream_synthesize_result(
        self,
        text: str,
        *,
        voice_id: str,
        speed: float,
        emotion: str = "",
        cancel_event: threading.Event | None = None,
    ) -> VoiceSynthesisResult: ...


class ManagedVoiceProvider(TtsProvider, Protocol):
    """Optional cloning operations; only providers declaring voice_cloning implement it."""

    def clone_voice(
        self, audio: bytes, *, file_name: str = "voice-clone.wav"
    ) -> VoiceCloneResult: ...
    def delete_voice(self, voice_id: str) -> None: ...


class VoiceCapability(Protocol):
    """Registrations belong to the plugin effect scope and disappear on unload."""

    @property
    def http(self) -> VoiceHttp: ...

    def register_asr(self, provider: AsrProvider) -> None: ...
    def register_tts(self, provider: TtsProvider) -> None: ...


class VoicePluginContext(PluginRuntimeContext, Protocol):
    """Setup surface for voice plugins, requiring voice and config manifest grants."""

    @property
    def voice(self) -> VoiceCapability: ...
    @property
    def config(self) -> ConfigValues: ...
