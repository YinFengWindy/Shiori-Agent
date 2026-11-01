"""``[plugins.proactive]`` settings. ``enabled`` is the plugin enablement flag."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class ProactivePluginConfig(BaseModel):
    """Scene follow-up and relationship motives. Both default on.

    A non-boolean value is rejected when the host loads ``config.toml``.
    This model is the settings schema; unknown keys (including ``enabled``)
    are ignored.
    """

    model_config = ConfigDict(extra="ignore")

    scene_followup: bool = True
    relationship: bool = True
