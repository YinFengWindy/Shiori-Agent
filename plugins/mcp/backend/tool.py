"""Registered tools retain identity, never an unguarded session."""

from typing import TYPE_CHECKING, Any
from shiori_sdk.mcp import McpToolInfo
from shiori_sdk.tools import Tool, ToolResult
from .api import SourceCall

if TYPE_CHECKING:
    from .registry import McpServerRegistry


class McpToolWrapper(Tool):
    """Chat and sources enter the host gate on this exact object."""

    def __init__(
        self, server: str, registry: "McpServerRegistry", info: McpToolInfo, epoch: int
    ):
        self._server, self._registry, self._info, self._epoch = (
            server,
            registry,
            info,
            epoch,
        )

    @property
    def name(self) -> str:
        return f"mcp_{self._server}__{self._info.name}"

    @property
    def description(self) -> str:
        return f"[MCP:{self._server}] {self._info.description}"

    @property
    def parameters(self) -> dict[str, Any]:
        return dict(self._info.input_schema)

    async def execute(
        self, source_call: SourceCall | None = None, /, **kwargs: Any
    ) -> str | ToolResult:
        # Positional-only options cannot be supplied by model JSON kwargs.
        return await self._registry.call_checked(
            self._server,
            self._info.name,
            self._epoch,
            source_call or SourceCall(kwargs),
        )
