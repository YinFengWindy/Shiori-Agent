"""Neutral schema fixture for host configuration persistence and failed-setup repair."""

from pydantic import BaseModel, Field


class NumericConfig(BaseModel):
    """A bounded integer used to exercise configuration plumbing only."""

    capacity: int = Field(default=3, ge=2)


async def setup(ctx):
    """Fail setup when persisted values are invalid, leaving schema repair available."""
    NumericConfig.model_validate(ctx.config.as_dict())
