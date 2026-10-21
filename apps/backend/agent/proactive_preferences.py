"""Core proactive strategy switches."""

from typing import Any

from proactive_v2.config import ProactiveStrategiesConfig

_STRATEGY_KEYS = ("scene_followup", "relationship")


def load_proactive_preferences(data: dict[str, Any]) -> ProactiveStrategiesConfig:
    """Loads independent strategy switches. Omitted keys stay enabled."""
    raw = data.get("agent", {}).get("proactive_strategies", {})
    if not isinstance(raw, dict) or set(raw) - set(_STRATEGY_KEYS):
        raise ValueError(
            "agent.proactive_strategies only accepts " + ", ".join(_STRATEGY_KEYS)
        )
    if any(not isinstance(value, bool) for value in raw.values()):
        raise ValueError("agent.proactive_strategies switches must be boolean")
    return ProactiveStrategiesConfig(
        **{key: bool(raw.get(key, True)) for key in _STRATEGY_KEYS}
    )
