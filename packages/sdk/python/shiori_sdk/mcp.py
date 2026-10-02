"""MCP session contracts; the host owns stdio and process cleanup."""

from typing import Protocol
from dataclasses import dataclass
from .tools import ToolResult


class McpToolError(RuntimeError):
    """Represents a structured JSON-RPC error returned by an MCP tool."""

    def __init__(
        self,
        *,
        server: str,
        tool_name: str,
        message: str,
        code: int | None = None,
        data: object = None,
    ) -> None:
        self.server = server
        self.tool_name = tool_name
        self.message = message
        self.code = code
        self.data = data
        super().__init__(f"MCP tool error ({server}/{tool_name}): {message}")


@dataclass
class McpToolInfo:
    """A discovered remote tool schema."""

    name: str
    description: str
    input_schema: dict[str, object]


class McpSession(Protocol):
    """One owned stdio session with explicit startup, calls and awaited teardown."""

    async def connect(self) -> list[McpToolInfo]: ...
    async def call(
        self,
        tool_name: str,
        arguments: dict[str, object],
        *,
        timeout: float | None = None,
    ) -> str | ToolResult: ...
    async def disconnect(self) -> None: ...
