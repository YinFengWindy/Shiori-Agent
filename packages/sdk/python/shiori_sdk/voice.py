"""Shared speech service wire values; policies and state belong to plugins."""

from typing import Literal, TypedDict

ASR_CONTRACT = "shiori.asr.v1"
TTS_CONTRACT = "shiori.tts.v1"


class TranscriptionRequest(TypedDict):
    """One complete PCM WAV recording passed to an ASR service's transcribe method."""

    audio_base64: str
    format: Literal["wav"]


class TranscriptionResult(TypedDict):
    """Recognized text returned by the selected ASR implementation."""

    text: str


class SynthesisRequest(TypedDict):
    """Role context for synthesis; provider-specific sound settings stay private."""

    text: str
    role_id: str
    mood: str


class SynthesisResult(TypedDict):
    """One encoded audio result, with its actual format for native playback."""

    audio_base64: str
    format: Literal["wav", "mp3"]
