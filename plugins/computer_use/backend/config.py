"""Computer Use settings exposed in the existing plugin configuration form."""

from pydantic import BaseModel, Field


class ComputerUseConfig(BaseModel):
    """Bounds individual native operations without changing the current model."""

    timeout_seconds: int = Field(
        default=30, ge=5, le=120, description="单次操作超时（秒）"
    )
