from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class VoiceAsrConfig:
    """Configuration for the selected cloud speech-to-text provider."""

    enabled: bool = False
    provider: str = "tencent"
    base_url: str = "https://asr.tencentcloudapi.com/"
    secret_id: str = ""
    secret_key: str = ""


@dataclass(frozen=True)
class VoiceTtsConfig:
    """Configuration for the selected cloud text-to-speech provider."""

    enabled: bool = False
    provider: str = "minimax"
    base_url: str = "https://api.minimaxi.com/v1/t2a_v2"
    model: str = "speech-2.8-turbo"
    api_key: str = ""


@dataclass(frozen=True)
class VoiceConfig:
    """Groups global voice switches, input preferences, and providers."""

    enabled: bool = False
    hotkey: str = "Ctrl+Space"
    microphone_device_id: str = ""
    asr: VoiceAsrConfig = VoiceAsrConfig()
    tts: VoiceTtsConfig = VoiceTtsConfig()
