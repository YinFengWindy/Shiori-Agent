from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RoleTtsSettings:
    """Resolved voice settings for one assistant turn."""

    enabled: bool
    provider: str
    voice_id: str
    speed: float
    emotion: str
    mood: str


def resolve_role_tts_settings(runtime_config: object, mood: object) -> RoleTtsSettings:
    """Reads role-owned voice data while ignoring malformed optional fields."""

    config = runtime_config if isinstance(runtime_config, dict) else {}
    raw_tts = config.get("tts")
    tts = raw_tts if isinstance(raw_tts, dict) else {}
    enabled = tts.get("enabled", True) is not False
    provider = str(tts.get("provider", "minimax")).strip()
    raw_providers = tts.get("providers")
    providers = raw_providers if isinstance(raw_providers, dict) else {}
    scoped = providers.get(provider)
    settings = scoped if isinstance(scoped, dict) else ({} if providers else tts)
    voice_id = str(settings.get("voice_id") or "").strip()
    raw_speed = settings.get("speed", 1.0)
    speed = float(raw_speed) if isinstance(raw_speed, (int, float)) else 1.0
    if not 0.5 <= speed <= 2.0:
        speed = 1.0
    mood_name = str(mood or "").strip()
    raw_mapping = settings.get("mood_tts_emotions")
    mapping = raw_mapping if isinstance(raw_mapping, dict) else {}
    candidate = str(mapping.get(mood_name) or "").strip().lower()
    # Provider capability validation belongs to VoiceService at call time.
    emotion = candidate
    return RoleTtsSettings(
        enabled=enabled,
        provider=provider,
        voice_id=voice_id,
        speed=speed,
        emotion=emotion,
        mood=mood_name,
    )
