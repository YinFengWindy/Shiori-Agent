"""Explicit MCP session doubles for plugin lifecycle tests."""

from .contracts import McpToolInfo
from shiori_sdk.tools import ToolResult
from shiori_sdk.processes import Processes


class FakeMcpSession:
    """Patchable explicit connection double for plugin cancellation tests."""

    def __init__(
        self,
        name: str,
        command: list[str],
        env: dict[str, str] | None = None,
        cwd: str | None = None,
        *,
        processes: Processes | None = None,
        own_process_tree: bool = False,
        inherit_env: bool = True,
    ):
        self.name, self.command, self.env, self.cwd = name, command, env, cwd
        self.own_process_tree, self.inherit_env = own_process_tree, inherit_env

    async def connect(self) -> list[McpToolInfo]:
        """A successful fake session has no discovered tools by default."""
        return []

    async def call(
        self,
        tool_name: str,
        arguments: dict[str, object],
        *,
        timeout: float | None = None,
    ) -> str | ToolResult:
        """Require explicit test configuration for every native action."""
        raise AssertionError(f"Unconfigured MCP call: {tool_name}")

    async def disconnect(self) -> None:
        """The fake owns no operating-system resources."""
