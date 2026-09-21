"""One role's serialized MCP/browser lifetime and persistent profile lease."""

import asyncio
import hashlib
import os
from pathlib import Path
from uuid import uuid4
from typing import Any

from agent.mcp.client import McpClient, McpToolError
from agent.tools.base import ToolResult

from .config import BrowserUseConfig
from .daemon import BrowserDaemon
from .profile import ProfileLease
from .runtime import BrowserRuntime


class BrowserSession:
    """Owns one role profile and rejects work retained by a cancelled generation."""

    def __init__(
        self,
        root: Path,
        role_id: str,
        config: BrowserUseConfig,
        runtime: BrowserRuntime,
    ) -> None:
        identity = hashlib.sha256(role_id.encode()).hexdigest()
        self.profile = root / "profiles" / identity
        namespace = (
            "shiori-" + hashlib.sha256(str(root.resolve()).encode()).hexdigest()[:16]
        )
        self.name = "role-" + identity[:16] + "-" + uuid4().hex[:12]
        self._runtime, self._config = runtime, config
        # Explicit config and filtered env prevent the user's agent-browser setup
        # from redirecting our actions into an external browser or another profile.
        self._env = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith("AGENT_BROWSER_")
        }
        root.mkdir(parents=True, exist_ok=True)
        config_path = root / "run" / (self.name + ".json")
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_path.write_text("{}", encoding="utf-8")
        self._env.update(
            AGENT_BROWSER_SESSION=self.name,
            AGENT_BROWSER_NAMESPACE=namespace,
            AGENT_BROWSER_PROFILE=str(self.profile),
            AGENT_BROWSER_EXECUTABLE_PATH=str(runtime.chrome),
            AGENT_BROWSER_HEADED="true" if config.headed else "false",
            AGENT_BROWSER_CONFIG=str(config_path),
            AGENT_BROWSER_IDLE_TIMEOUT_MS="0",
            AGENT_BROWSER_SOCKET_DIR=str(root / "run"),
        )
        self._client: McpClient | None = None
        self._daemon: BrowserDaemon | None = None
        self._lease: ProfileLease | None = None
        self._lock = asyncio.Lock()
        self._closed = False

    @property
    def closed(self) -> bool:
        """Whether this generation can no longer accept actions."""
        return self._closed

    def stop(self) -> None:
        """Closes admission before the manager cancels this generation's actions."""
        self._closed = True

    async def _start(self) -> None:
        self._lease = ProfileLease(self.profile)
        # The CLI's auto-spawned daemon loses its stderr reader when CLI exits.
        # Owning the daemon directly keeps diagnostics valid (including tab close).
        self._daemon = BrowserDaemon(
            self._runtime.agent_browser, self.profile, self._env
        )
        await self._daemon.start(self._config.timeout_seconds)
        self._client = McpClient(
            "browser_use",
            [str(self._runtime.agent_browser), "mcp", "--tools", "core"],
            env=self._env,
            cwd=str(self.profile),
            own_process_tree=True,
            inherit_env=False,
        )
        await self._client.connect()

    async def call(self, name: str, arguments: dict[str, Any]) -> str | ToolResult:
        """Serializes actions and closes the entire generation on cancellation or transport failure."""
        async with self._lock:
            if self._closed:
                raise RuntimeError("Browser Use 会话已停止，请重新调用工具")
            try:
                if self._client is None:
                    await self._start()
                if self._closed:
                    raise RuntimeError("Browser Use 会话已停止，请重新调用工具")
                if self._client is None:
                    raise RuntimeError("Browser Use MCP 连接未建立")
            except BaseException:
                # Initialization/listing errors are startup failures even when
                # represented by McpToolError; no usable page exists yet.
                self.stop()
                await self._dispose()
                raise
            try:
                if name == "agent_browser_screenshot":
                    screenshots = self.profile.parent.parent / "screenshots"
                    screenshots.mkdir(parents=True, exist_ok=True)
                    arguments = {
                        **arguments,
                        "path": str(
                            screenshots
                            / (
                                self.name
                                + (
                                    ".jpg"
                                    if arguments.get("format") == "jpeg"
                                    else ".png"
                                )
                            )
                        ),
                    }
                result = await self._client.call(
                    name,
                    {
                        **arguments,
                        "session": self.name,
                        "timeoutMs": self._config.timeout_seconds * 1000,
                    },
                    timeout=self._config.timeout_seconds,
                )
                return result
            except McpToolError:
                # A completed action error (e.g. stale ref) needs a fresh snapshot,
                # not a lost page. Transport interruption invalidates the generation.
                raise
            except BaseException:
                self.stop()
                await self._dispose()
                raise

    async def close(self, *, graceful: bool = False) -> None:
        """Stops owned input-capable processes before releasing the persistent profile."""
        self.stop()
        async with self._lock:
            await self._dispose(graceful=graceful)

    async def _dispose(self, *, graceful: bool = False) -> None:
        # Both the action failure path and public close hold _lock here.
        try:
            if self._client is not None:
                try:
                    if graceful:
                        await self._client.call(
                            "agent_browser_close", {"session": self.name}, timeout=5
                        )
                finally:
                    await self._client.disconnect()
                    self._client = None
        finally:
            try:
                if self._daemon is not None:
                    await self._daemon.close()
                    self._daemon = None
            finally:
                if self._lease is not None:
                    self._lease.close()
                    self._lease = None
