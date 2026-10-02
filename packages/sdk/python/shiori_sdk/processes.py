"""Injected process ownership and turn lifetime; SDK never launches native children."""

import asyncio
import subprocess
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import BinaryIO, Protocol
from .mcp import McpSession


class ProcessOwner(Protocol):
    """Synchronous ownership handle that kills all children when closed."""

    def close(self) -> None: ...


class ToolTurn(Protocol):
    """Unforgeable host turn identity with awaited finalizers."""

    @property
    def closed(self) -> bool: ...
    def own(self, key: object, release: Callable[[], Awaitable[None]]) -> None: ...


class Processes(Protocol):
    """Host process services shared by browser, computer and channel adapters."""

    def mcp(
        self,
        name: str,
        command: list[str],
        env: dict[str, str] | None = None,
        cwd: str | None = None,
        *,
        own_process_tree: bool = False,
        inherit_env: bool = True,
    ) -> McpSession: ...

    async def spawn(
        self,
        *command: str,
        env: dict[str, str],
        cwd: str,
        stdin: int,
        stdout: BinaryIO,
        stderr: BinaryIO,
    ) -> tuple[asyncio.subprocess.Process, ProcessOwner | None]: ...

    def popen(
        self,
        command: list[str],
        *,
        cwd: Path,
        env: dict[str, str],
        stdout: BinaryIO,
        stderr: int | BinaryIO,
    ) -> tuple[subprocess.Popen[bytes], ProcessOwner | None]:
        """Start a synchronous child with host-selected tree ownership before execution."""
        ...


class Resources(Protocol):
    """Explicit source/frozen paths and shared emoji locations selected by the host."""

    @property
    def root(self) -> Path: ...
    def common_emojis(self, workspace: Path) -> tuple[Path, ...]: ...
