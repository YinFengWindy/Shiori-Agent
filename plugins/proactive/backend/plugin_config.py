"""``[plugins.proactive]`` settings. ``enabled`` is the plugin enablement flag."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, StrictBool


class ProactivePluginConfig(BaseModel):
    """Scene follow-up and relationship motives. Both default on.

    A non-boolean value fails ``setup`` (and ``plugin.config.set``). Unknown
    keys, ``enabled`` included, are ignored.
    """

    model_config = ConfigDict(extra="ignore")

    scene_followup: StrictBool = True
    relationship: StrictBool = True
