"""Scene follow-up and relationship switches from ``[plugins.proactive]``.

Omitted keys stay on. ``enabled`` is the plugin's own enablement and is not
read here.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .config import ProactiveStrategiesConfig

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
