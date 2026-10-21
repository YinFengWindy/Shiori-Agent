"""Core scene observation switch."""

from typing import Any


def load_scene_preferences(data: dict[str, Any]) -> bool:
    """Loads the core scene switch. Omitted keys stay enabled."""
    raw = data.get("agent", {}).get("scene_observation", {})
    if not isinstance(raw, dict) or set(raw) - {"enabled"}:
        raise ValueError("agent.scene_observation only accepts enabled")
    if any(not isinstance(value, bool) for value in raw.values()):
        raise ValueError("agent.scene_observation switches must be boolean")
    return bool(raw.get("enabled", True))
