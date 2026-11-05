"""Declared-dependency export, not a new SDK capability."""

from dataclasses import dataclass
from typing import Protocol, runtime_checkable
from shiori_sdk.tools import ToolResult


@dataclass(frozen=True)
class SourceCall:
    """Source options which JSON tool arguments cannot construct."""

    arguments: dict[str, object]
    timeout: float | None = None
    retry_on_transport: bool = False


@runtime_checkable
class McpAPI(Protocol):
    """Resolve afresh for each operation through optional dependencies."""

    async def call(
        self,
        server: str,
        tool: str,
        arguments: dict[str, object],
        *,
        timeout: float | None = None,
        retry_on_transport: bool = False,
    ) -> str | ToolResult: ...
