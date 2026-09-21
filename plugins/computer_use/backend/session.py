"""One exclusively leased Driver generation with serialized target operations."""

import asyncio
from pathlib import Path
from typing import Any

from agent.mcp.client import McpClient
from agent.tools.base import ToolResult

from .config import ComputerUseConfig
from .lease import DesktopLease
from .runtime import driver_client, resolve_driver
from .targets import WindowTargets


class DesktopSession:
    """Owns only Driver children; existing desktop applications are never terminated."""

    def __init__(self, root: Path, config: ComputerUseConfig) -> None:
        self._root, self._config = root, config
        self._client: McpClient | None = None
        self._lease: DesktopLease | None = None
        self._lock = asyncio.Lock()
        self._targets = WindowTargets()
        self.stopped = False
        self.ready = False

    def stop(self) -> None:
        """Closes admission synchronously, including callers queued on the lock."""
        self.stopped = True

    async def call(self, name: str, arguments: dict[str, Any]) -> str | ToolResult:
        """Bounds startup and observation/action together; errors propagate to the owner."""
        async with self._lock:
            if self.stopped:
                raise RuntimeError("Computer Use 任务已停止")
            async with asyncio.timeout(self._config.timeout_seconds):
                if self._client is None:
                    executable = resolve_driver()
                    self._lease = DesktopLease()
                    self._client = driver_client(self._root, executable)
                    await self._client.connect()
                    self.ready = True
                if self.stopped:
                    raise RuntimeError("Computer Use 任务已停止")
                identity = self._targets.validate(name, arguments)
                native_arguments = dict(arguments)
                native_arguments.pop("observation_id", None)
                if (
                    not arguments.get("element_token")
                    and "element_index" not in arguments
                ):
                    # Driver v0.28.2 rejects snapshot_id on pixel/keyboard actions.
                    # Host still requires and checks it before removing that field.
                    native_arguments.pop("snapshot_id", None)
                result = await self._client.call(
                    name, native_arguments, timeout=self._config.timeout_seconds
                )
                if name == "get_window_state" and identity is not None:
                    self._targets.remember(identity, result)
                return result

    async def close(self) -> None:
        """Releases desktop ownership only after every input-capable child is gone."""
        self.stop()
        async with self._lock:
            if self._client is not None:
                await self._client.disconnect()
                self._client = None
            if self._lease is not None:
                self._lease.close()
                self._lease = None
