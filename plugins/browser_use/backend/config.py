"""Validated settings exposed through the existing plugin configuration form."""

from pydantic import BaseModel, Field


class BrowserUseConfig(BaseModel):
    """Controls visibility and the deadline of a single browser action."""

    headed: bool = Field(default=False, description="显示浏览器窗口")
    timeout_seconds: int = Field(
        default=45, ge=5, le=120, description="单次操作超时（秒）"
    )
