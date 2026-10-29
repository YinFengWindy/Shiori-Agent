"""``[plugins.scene]`` observation switch."""

from __future__ import annotations

from pydantic import BaseModel, Field


class SceneConfig(BaseModel):
    """Plugin-owned scene settings. ``enabled`` stays a host flag."""

    observation_enabled: bool = Field(default=True, title="场景观察")
