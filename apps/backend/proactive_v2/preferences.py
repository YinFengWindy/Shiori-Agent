"""Host switches for scene follow-up and relationship motives.

They live in ``[plugins.proactive]`` (the same table as the future plugin's
enablement). Omitted keys stay on. ``enabled`` and any other plugin keys are
left for the plugin; this reader only interprets the two switches the host
still wires until the proactive loop moves.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from proactive_v2.config import ProactiveStrategiesConfig

# The only keys ``[agent.proactive_strategies]`` ever had; the startup
# migration moves exactly these.
STRATEGY_KEYS = ("scene_followup", "relationship")


def load_proactive_preferences(
    plugins: Mapping[str, Any],
) -> ProactiveStrategiesConfig:
    """Loads the two switches. A missing table or key stays enabled."""
    # ``Config.plugins`` only keeps tables, so a present value is a dict.
    raw = plugins.get("proactive", {})
    for key in STRATEGY_KEYS:
        if key in raw and not isinstance(raw[key], bool):
            raise ValueError(f"plugins.proactive.{key} 必须是布尔值")
    return ProactiveStrategiesConfig(
        **{key: bool(raw.get(key, True)) for key in STRATEGY_KEYS}
    )
