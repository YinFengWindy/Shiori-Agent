"""Test harness over the real kernel: stub services in, plugins started, watchers awaited."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from typing import Any

from shiori_sdk.kernel import Kernel, Key, PluginSpec


class KernelHarness:
    """Runs plugin specs on a real ``Kernel`` with stub core services.

    ``services`` maps core keys to stubs, provided before any plugin starts.
    ``idle`` exists only here, not on the plugin context (D15): ``watch``
    delivery is fire-and-forget, so a test awaits it explicitly.
    """

    def __init__(
        self,
        services: Mapping[Key[Any], object] | None = None,
        *,
        kernel: Kernel | None = None,
    ) -> None:
        self.kernel = kernel or Kernel()
        for key, service in (services or {}).items():
            self.kernel.provide(key, service)

    async def start(self, *specs: PluginSpec) -> Kernel:
        """Starts ``specs`` in dependency order and returns the kernel."""
        await self.kernel.start(specs)
        return self.kernel

    async def idle(self) -> None:
        """Waits until every queued ``watch`` delivery has run."""
        queues = self.kernel._events._queues  # pyright: ignore[reportPrivateUsage]
        while busy := [
            queue.worker
            for queue in queues.values()
            if queue.worker is not None and not queue.worker.done()
        ]:
            _ = await asyncio.gather(*busy, return_exceptions=True)

    async def stop(self) -> list[Exception]:
        """Stops every running plugin; returns the cleanup errors."""
        return await self.kernel.stop()
