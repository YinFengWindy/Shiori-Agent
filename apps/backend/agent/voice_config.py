from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class VoiceAsrConfig:
    """Host-owned recognition switch and provider selection."""

    enabled: bool = False
    provider: str = "tencent"


@dataclass(frozen=True)
class VoiceTtsConfig:
    """Host-owned synthesis switch and default provider selection."""

    enabled: bool = False
    provider: str = "minimax"


@dataclass(frozen=True)
class VoiceConfig:
    """Groups global voice switches, input preferences, and providers."""

    enabled: bool = False
    hotkey: str = "Ctrl+Space"
    microphone_device_id: str = ""
    asr: VoiceAsrConfig = VoiceAsrConfig()
    tts: VoiceTtsConfig = VoiceTtsConfig()
