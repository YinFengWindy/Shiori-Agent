"""``[plugins.memory_optimizer]`` settings. ``enabled`` stays a host flag."""

from __future__ import annotations

from pydantic import BaseModel, Field

# Every 18 hours, aligned to whole hours.
DEFAULT_INTERVAL_SECONDS = 64800


class MemoryOptimizerConfig(BaseModel):
    """How often every role's memory is optimized."""

    interval_seconds: int = Field(
        default=DEFAULT_INTERVAL_SECONDS,
        ge=60,
        title="整理间隔",
        json_schema_extra={"unit": "秒"},
    )
