from __future__ import annotations

from dataclasses import dataclass


class VoiceServiceError(RuntimeError):
    """Raised when a voice provider rejects a request or returns invalid data."""

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
    """Non-sensitive provider diagnostics for one ASR or TTS operation."""

    provider: str
    request_id: str
    elapsed_ms: int
    audio_duration_ms: int
    character_count: int
    error_code: str = ""

    def to_dict(self) -> dict[str, str | int]:
        """Serializes metrics for bridge payloads and message metadata."""

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
    """Carries recognized text with non-sensitive request diagnostics."""

    text: str
    metrics: VoiceOperationMetrics


@dataclass(frozen=True)
class VoiceSynthesisResult:
    """Carries one synthesized sentence with non-sensitive request diagnostics."""

    audio: bytes
    metrics: VoiceOperationMetrics
