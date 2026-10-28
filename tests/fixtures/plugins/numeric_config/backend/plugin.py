"""Neutral schema fixture for host configuration persistence and failed-setup repair."""

from pydantic import BaseModel, Field

from shiori_sdk.core.services import CONFIG


class NumericConfig(BaseModel):
    """A bounded integer used to exercise configuration plumbing only."""

    capacity: int = Field(default=3, ge=2)


async def setup(ctx):
    """Fail setup when persisted values are invalid, leaving schema repair available."""
    NumericConfig.model_validate(ctx.require(CONFIG).as_dict())
