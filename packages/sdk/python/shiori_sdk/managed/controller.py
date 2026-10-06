"""Background preparation and explicit service controls for a private runtime."""

import asyncio
import platform
from collections.abc import Awaitable, Callable
from pathlib import Path

from shiori_sdk.extensions import BackgroundTasks

from .installation import Installation
from .service import OwnedService


class ManagedRuntime:
    """Expose cancellable progress without tying multi-GB work to an RPC lifetime."""

    def __init__(
        self,
        installation: Installation,
        service: OwnedService,
        background: BackgroundTasks,
        build: Callable[[Path], Awaitable[None]],
        mode: Callable[[], str],
    ):
        self.installation, self.service = installation, service
        self.background, self.build, self.mode = background, build, mode
        self.task: asyncio.Task[None] | None = None
        self.phase, self.error, self.item = "stopped", "", ""
        self.received = self.total = 0
        self.closed = False

    def status(self) -> dict[str, object]:
        """Return preparation progress and actual owned-process availability."""
        process = self.service.child.process
        running = process is not None and process.returncode is None
        installation_error = ""
        try:
            installed = self.installation.current() is not None
        except ValueError as error:
            installed, installation_error = False, str(error)
        return {
            "phase": self.phase if self.phase != "ready" or running else "stopped",
            "error": self.error or installation_error,
            "item": self.item,
            "received": self.received,
            "total": self.total,
            "installed": installed,
            "running": running,
            "busy": self.task is not None and not self.task.done(),
            "revision": self.installation.revision,
        }

    def submit(
        self, action: str, source: Path | None = None, import_asset: str | None = None
    ):
        """Accept one action; observable failures remain in status until the next action."""
        if self.closed or (self.task is not None and not self.task.done()):
            raise RuntimeError("环境正在执行其他操作")
        if platform.system() != "Windows" or platform.machine().lower() not in {
            "amd64",
            "x86_64",
        }:
            raise RuntimeError("此托管环境仅支持 Windows x64")
        self.error = ""
        self.phase = "preparing" if action == "prepare" else "starting"
        self.task = self.background.spawn(
            self._run(action, source, import_asset), name="managed-runtime"
        )
        return self.status()

    async def _run(self, action: str, source: Path | None, import_asset: str | None):
        try:
            if action == "prepare":
                path = await self.installation.prepare(
                    self.build, self._progress, source=source, import_asset=import_asset
                )
            else:
                path = self.installation.current()
            if path is None:
                raise RuntimeError("尚未准备托管环境")
            if self.mode() == "managed":
                self.phase = "starting"
                await self.service.close()
                await self.service.start(path)
            if action == "prepare":
                self.installation.publish(path)
            self.phase = "ready" if self.service.url else "stopped"
        except asyncio.CancelledError:
            self.phase = "cancelled"
            raise
        except Exception as error:
            # This is the background-operation boundary; the settings UI polls this error.
            self.phase, self.error = "error", str(error)
        finally:
            if source is not None:
                source.unlink(missing_ok=True)

    def _progress(self, item: str, received: int, total: int):
        self.item, self.received, self.total = item, received, total

    async def cancel(self) -> None:
        """Cancel preparation and wait until all staging writes and subprocesses end."""
        if self.task is not None and not self.task.done():
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)

    async def stop(self) -> None:
        """Explicitly stop the managed service; this is separate from discarding playback."""
        await self.cancel()
        await self.service.close()
        self.phase = "stopped"

    async def close(self) -> None:
        """Prevent further work before plugin draining releases runtime leases."""
        self.closed = True
        await self.stop()
