"""Validated settings exposed through the existing plugin configuration form."""

from pydantic import BaseModel, Field
from typing import Literal


class BrowserUseConfig(BaseModel):
    """Controls visibility and the deadline of a single browser action."""

    backend: Literal["agent-browser", "ego(lite)"] = Field(
        default="agent-browser", title="浏览器后端"
    )
    headed: bool = Field(default=False, title="显示浏览器窗口（agent-browser）")
    ego_browser_path: str = Field(default="", title="ego-browser 路径")
    timeout_seconds: int = Field(
        default=45, ge=5, le=120, title="单次操作超时", json_schema_extra={"unit": "秒"}
    )
