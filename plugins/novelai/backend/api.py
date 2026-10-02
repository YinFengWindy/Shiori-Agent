"""Public NovelAI export consumed by explicitly declared sibling dependencies."""

from typing import Protocol, runtime_checkable
from shiori_sdk.tools import ToolResult


@runtime_checkable
class ImageGenerationAPI(Protocol):
    """Submit NovelAI parameters and return generation text or a typed tool result."""

    async def execute(self, **kwargs: object) -> str | ToolResult: ...
