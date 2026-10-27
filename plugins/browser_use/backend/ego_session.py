"""Role-owned ego Space generations with acknowledged remote cancellation."""

import asyncio
import base64
import hashlib
import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from shiori_sdk.media import detect_image_mime_from_header
from shiori_sdk.processes import Processes
from shiori_sdk.tools import ToolResult

from .config import BrowserUseConfig
from .ego_command import EgoActionError, EgoCommand
from .ego_runtime import EgoRuntime


class EgoSession:
    """Serialize one role's actions; only release a generation after Space cleanup."""

    def __init__(
        self,
        root: Path,
        role_id: str,
        config: BrowserUseConfig,
        runtime: EgoRuntime,
        processes: Processes,
    ) -> None:
        identity = hashlib.sha256(role_id.encode()).hexdigest()
        workspace = hashlib.sha256(str(root.resolve()).encode()).hexdigest()[:12]
        generation = uuid4().hex
        self.root = root / "ego" / identity / generation
        self.root.mkdir(parents=True, exist_ok=True)
        self.name = f"Shiori {workspace} role {identity[:12]} task {generation}"
        self._command = EgoCommand(self.root, runtime, processes)
        self._config = config
        self._closed = False
        self._started = False
        self._start_requested = False
        self._disposed = False
        self._lock = asyncio.Lock()
        self._inflight: asyncio.Task[dict[str, Any]] | None = None
        self._cleanup: asyncio.Task[None] | None = None

    @property
    def closed(self) -> bool:
        """A stopped generation never accepts further browser actions."""
        return self._closed

    def stop(self) -> None:
        """Invalidate admission in both Python and the embedded Node runtime."""
        self._closed = True
        (self.root / "stopped").touch()

    async def call(self, name: str, arguments: dict[str, Any]) -> str | ToolResult:
        """Retire uncertain/timeout failures; known ref errors can be re-observed."""
        async with self._lock:
            if self.closed:
                raise RuntimeError("Browser Use 会话已停止，请重新调用工具")
            try:
                if not self._started:
                    self._start_requested = True
                    await self._execute("start", {})
                    self._started = True
            except BaseException:
                self.stop()
                await self._dispose()
                raise
            try:
                response = await self._execute(
                    name.removeprefix("ego_browser_"), arguments
                )
                result = response["result"]
                if name == "ego_browser_screenshot":
                    data = (self.root / "screenshot.png").read_bytes()
                    mime = detect_image_mime_from_header(data)
                    if mime != "image/png" or len(data) > 20 * 1024 * 1024:
                        raise RuntimeError("ego(lite) 返回的截图无效或超过 20 MiB")
                    return ToolResult(
                        text="当前 ego(lite) 页面截图。",
                        content_blocks=[
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}"
                                },
                            }
                        ],
                    )
                return (
                    result
                    if isinstance(result, str)
                    else json.dumps(result, ensure_ascii=False)
                )
            except EgoActionError as error:
                if not error.recoverable:
                    self.stop()
                    await self._dispose()
                raise
            except BaseException:
                self.stop()
                await self._dispose()
                raise

    async def _execute(
        self, operation: str, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        task = asyncio.create_task(
            self._command.run(
                {
                    "operation": operation,
                    "name": self.name,
                    "arguments": arguments,
                    "timeout": self._config.timeout_seconds * 1000,
                }
            )
        )
        self._inflight = task
        async with asyncio.timeout(self._config.timeout_seconds):
            # Stopping a CLI alone leaves embedded scripts alive. Keep it owned
            # until the remote Space has acknowledged its disposal.
            response = await asyncio.shield(task)
        self._inflight = None
        return response

    async def close(self, *, graceful: bool = False) -> None:
        """Finish our Space without terminating the user's browser or other tasks."""
        self.stop()
        async with self._lock:
            await self._dispose()

    async def _dispose(self) -> None:
        if self._cleanup is None:
            self._cleanup = asyncio.create_task(self._dispose_remote())
        try:
            await asyncio.shield(self._cleanup)
        except asyncio.CancelledError:
            raise
        except BaseException:
            # A failed acknowledgment retains this stopped generation for retry.
            self._cleanup = None
            raise

    async def _dispose_remote(self) -> None:
        if self._disposed:
            return
        if self._start_requested and not self._started:
            if self._inflight is None:
                raise RuntimeError("无法确认 ego 任务创建状态，保留已停止的会话")
            rejected = False
            try:
                # Startup performs no page action and self-disposes after a
                # cancellation latch. Await its receipt to avoid double-finishing
                # a Space created concurrently with cancellation.
                async with asyncio.timeout(10):
                    await asyncio.shield(self._inflight)
            except EgoActionError:
                rejected = True  # An explicit runner error proves startup ended.
            except Exception:
                if not (self.root / "space.json").is_file():
                    raise
                # A lost CLI receipt must not make a published Space impossible
                # to clean up. Its exact identity remains sufficient to close it.
            if not rejected and not (self.root / "space.json").is_file():
                raise RuntimeError("ego 任务缺少创建确认，无法确认远端操作已停止")
        if (self.root / "space.json").is_file():
            async with asyncio.timeout(10):
                await self._command.run({"operation": "close"})
        self._disposed = True
        if self._inflight is not None:
            self._inflight.cancel()
            await asyncio.gather(self._inflight, return_exceptions=True)
            self._inflight = None
