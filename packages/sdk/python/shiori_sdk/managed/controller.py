"""Background preparation and explicit service controls for a private runtime."""

import asyncio
import platform
from collections.abc import Callable
from pathlib import Path

from shiori_sdk.extensions import BackgroundTasks

from .installation import Build, Installation, free_space
from .paths import environment_path
from .service import OwnedService, ServiceRunning

# Phases that only exist while a task runs; a task cancelled before its first
# step never reaches its own handler, so status() resolves them afterwards.
_TRANSIENT = frozenset({"preparing", "starting", "removing"})


async def _join_thread(
    function: Callable[[], None],
) -> tuple[Exception | None, bool]:
    """Run filesystem work in a thread that cancellation cannot abandon.

    A cancelled wait would leave the thread deleting files while holding the
    leases. The work is shielded and joined; its failure is returned together
    with whether cancellation was requested meanwhile, so the caller records
    the real outcome and then still re-raises the cancellation.
    """
    work = asyncio.ensure_future(asyncio.to_thread(function))
    cancelled = False
    while True:
        try:
            await asyncio.shield(work)
            return None, cancelled
        except asyncio.CancelledError:
            if work.done() and work.cancelled():
                raise
            cancelled = True
        except Exception as error:
            return error, cancelled


class ManagedRuntime:
    """Expose cancellable progress without tying multi-GB work to an RPC lifetime.

    ``import_asset`` names the single artifact a non-ZIP import provides; a
    ZIP import always carries every artifact.
    """

    def __init__(
        self,
        installation: Installation,
        service: OwnedService,
        background: BackgroundTasks,
        build: Build,
        mode: Callable[[], str],
        *,
        import_asset: str | None = None,
    ):
        if import_asset is not None and import_asset not in {
            item.name for item in installation.artifacts
        }:
            raise ValueError("导入资源不在固定资源清单中")
        self.installation, self.service = installation, service
        self.background, self.build, self.mode = background, build, mode
        self.import_asset = import_asset
        self.task: asyncio.Task[None] | None = None
        self.phase, self.error, self.item = "stopped", "", ""
        self.received = self.total = 0
        self.closed = False
        # Kept download bytes, leftover staging, whether a removal has work and
        # the space a download / an import needs. Measured only while no task
        # runs; a task marks it stale and status keeps the last measurement.
        self._footprint: tuple[int, bool, bool, int, int] = (0, False, True, 0, 0)
        self._stale = True

    def _measure(self) -> tuple[int, bool, bool, int, int]:
        installation = self.installation
        return (
            *installation.reclaimable(),
            installation.occupied(),
            installation.required(),
            # The import offered first: the single artifact in place, else a ZIP.
            installation.required(
                imported=self.import_asset, bundle=self.import_asset is None
            ),
        )

    def _running(self) -> bool:
        process = self.service.child.process
        return process is not None and process.returncode is None

    def status(self) -> dict[str, object]:
        """Return preparation progress and actual owned-process availability."""
        running = self._running()
        busy = self.task is not None and not self.task.done()
        installation_error = ""
        try:
            installed = self.installation.current() is not None
        except ValueError as error:
            installed, installation_error = False, str(error)
        phase = self.phase
        if phase == "ready" and not running:
            phase = "stopped"
        elif phase in _TRANSIENT and not busy:
            phase = "cancelled"
        try:
            location: Path | None = self.installation.install_root
            location_error = ""
        except ValueError as error:
            # Reported, not raised: relocating or removing recovers from it.
            location, location_error = None, str(error)
        if busy or location is None:
            self._stale = True
        elif self._stale:
            self._footprint, self._stale = self._measure(), False
        reclaimable, staging, occupied, required, required_import = self._footprint
        if location is None:
            occupied = True
        return {
            "phase": phase,
            "error": self.error or installation_error or location_error,
            "item": self.item,
            "received": self.received,
            "total": self.total,
            "installed": installed,
            "running": running,
            "busy": busy,
            "revision": self.installation.revision,
            # Kept downloads/staging a removal frees, also without an installation.
            "reclaimable": reclaimable,
            "staging": staging,
            # Install root ("" while its record is unreadable), whether it is a
            # chosen one, the space a download / an import needs and the free
            # space of its volume.
            "location": "" if location is None else environment_path(location),
            "customized": self.installation.customized(),
            "required": required,
            "required_import": required_import,
            "free": None if location is None else free_space(location),
            # Whatever blocks a location change is removable, and vice versa.
            "removable": occupied,
            # An unreadable record can be replaced while no pointer exists.
            "relocatable": not busy
            and (
                not self.installation.pointer.exists()
                if location is None
                else not occupied
            ),
        }

    def submit(self, action: str, source: Path | None = None):
        """Accept one action; observable failures remain in status until the next action.

        ``source`` is the user's original import file; it is read, never deleted.
        """
        self._admit()
        if platform.system() != "Windows" or platform.machine().lower() not in {
            "amd64",
            "x86_64",
        }:
            raise RuntimeError("此托管环境仅支持 Windows x64")
        self.error, self._stale = "", True
        self.phase = "preparing" if action == "prepare" else "starting"
        self.task = self.background.spawn(
            self._run(action, source), name="managed-runtime"
        )
        return self.status()

    def remove(self):
        """Delete the installation in the background; only a stopped, idle runtime."""
        self._admit()
        if self._running():
            raise RuntimeError("请先停止环境")
        self.error, self.phase, self._stale = "", "removing", True
        self.item, self.received, self.total = "", 0, 0
        self.task = self.background.spawn(self._remove(), name="managed-runtime")
        return self.status()

    def relocate(self, root: Path | None):
        """Install future preparations under ``root``, or the default with ``None``.

        Nothing may be installed or kept, and no task may run.
        """
        self._admit()
        self.installation.relocate(root)
        self.error, self._stale = "", True
        return self.status()

    def _admit(self) -> None:
        if self.closed or (self.task is not None and not self.task.done()):
            raise RuntimeError("环境正在执行其他操作")

    async def _remove(self):
        def remove():
            # Both leases are taken inside the thread: a cancelled wait cannot
            # release them while files are still being deleted.
            with self.service.idle():
                self.installation.remove()

        error, cancelled = await _join_thread(remove)
        # Record the real outcome, even when cancellation arrived meanwhile;
        # this is the background-operation boundary the settings UI polls.
        if error is not None:
            self.phase, self.error = "error", str(error)
        else:
            self.phase = "stopped"
        if cancelled:
            raise asyncio.CancelledError

    def _discard_superseded(self, published: Path) -> None:
        """Prune caches and versions no service of any generation can still use."""
        if self._running():
            self.installation.discard_superseded(
                keep_versions=self.service.installation != published
            )
            return
        try:
            with self.service.idle():
                self.installation.discard_superseded(keep_versions=False)
        except ServiceRunning:
            # Another generation's service may run from an older version.
            self.installation.discard_superseded(keep_versions=True)

    async def _run(self, action: str, source: Path | None):
        published = False
        try:
            if action == "prepare":
                path = await self.installation.prepare(
                    self.build,
                    self._progress,
                    source=source,
                    import_asset=self.import_asset,
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
                published = True
                # Only a published success drops the cache; failures keep it to resume.
                error, cancelled = await _join_thread(
                    lambda: self._discard_superseded(path)
                )
                if error is not None:
                    # The published version stays usable; only cleanup failed.
                    self.error = f"清理旧版本或下载缓存失败：{error}"
                if cancelled:
                    raise asyncio.CancelledError
            self.phase = "ready" if self.service.url else "stopped"
        except asyncio.CancelledError:
            # A published version stays usable; only unfinished work is cancelled.
            self.phase = (
                ("ready" if self.service.url else "stopped")
                if published
                else "cancelled"
            )
            raise
        except Exception as error:
            # This is the background-operation boundary; the settings UI polls this error.
            self.phase, self.error = "error", str(error)

    def _progress(self, item: str, received: int, total: int):
        self.item, self.received, self.total = item, received, total

    async def cancel(self) -> None:
        """Cancel the task and wait until its writes, deletions and subprocesses end."""
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
