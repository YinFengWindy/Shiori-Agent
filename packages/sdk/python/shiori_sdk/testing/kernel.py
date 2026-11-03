"""Test harness over the real kernel: stub services in, plugins started, watchers awaited."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from typing import Any

from shiori_sdk.kernel import Kernel, KernelError, KernelState, Key, PluginSpec

DRAIN_TIMEOUT = 60.0
"""Seconds a harness reload waits for its closure to drain (D25)."""


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
        # A later plan can exclude a still-running plugin from order(). Remember
        # running ids so stop also releases those missing from the current plan.
        self._started = dict.fromkeys(
            plugin_id
            for plugin_id in self.kernel.order()
            if (status := self.kernel.status(plugin_id)) is not None
            and status.state is KernelState.ACTIVE
        )
        for key, service in (services or {}).items():
            self.kernel.provide(key, service)

    async def start(self, *specs: PluginSpec) -> Kernel:
        """Starts only the supplied runnable specs, in dependency order.

        Previously planned plugins are not retried implicitly, and active
        plugins keep their current instance.
        """
        selected = {spec.id for spec in specs if spec.runnable}
        for plugin_id in await self.kernel.plan(specs):
            status = self.kernel.status(plugin_id)
            if plugin_id in selected and (
                status is None or status.state is not KernelState.ACTIVE
            ):
                activated = await self.kernel.activate(plugin_id)
                if activated.state is KernelState.ACTIVE:
                    self._started[plugin_id] = None
        return self.kernel

    async def reload(
        self, plugin_id: str, *, timeout: float = DRAIN_TIMEOUT
    ) -> tuple[str, ...]:
        """Drains and replaces a running plugin and its optional consumers.

        A restart-only member refuses the whole closure before draining.
        Drain failures leave the old instances intact.
        """
        status = self.kernel.status(plugin_id)
        if status is None or status.state is not KernelState.ACTIVE:
            reason = f"插件 {plugin_id} 未在运行，无法重载"
            raise KernelError("not_active", "reload", "state", reason, [plugin_id])
        members = self.kernel.closure(plugin_id, optional=True)
        if refusal := self.kernel.restart_only(members):
            raise refusal
        await self.kernel.drain(members, timeout)
        for member in members:
            _ = await self.kernel.deactivate(member)
            _ = self._started.pop(member, None)
        order = tuple(reversed(members))
        for member in order:
            activated = await self.kernel.activate(member)
            if activated.state is KernelState.ACTIVE:
                self._started[member] = None
        return order

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
        errors: list[Exception] = []
        # Current dependency order wins over activation history: an optional
        # consumer may have started before its provider. Excluded ids follow.
        order = dict.fromkeys((*reversed(self.kernel.order()), *self._started))
        for plugin_id in order:
            errors.extend(await self.kernel.deactivate(plugin_id))
            _ = self._started.pop(plugin_id, None)
        return errors
