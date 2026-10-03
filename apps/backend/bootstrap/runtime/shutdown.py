"""Ordered process shutdown while queued and detached tasks retain resources."""

import asyncio

from core.common.cleanup import run_cleanup_steps
from core.net.http import clear_default_shared_http_resources
from bootstrap.runtime.generations import RuntimeRetention


class RuntimeShutdownMixin:
    """Stops intake first, then drains accepted work before shared resources close."""

    async def shutdown(self) -> None:
        """Closes the process without leaving queued generation references behind."""
        if self._shutdown_task is None:
            self._shutdown = True
            self._generation_manager.close()
            retained = RuntimeRetention(self._generation_manager.tracked)
            self._shutdown_task = asyncio.create_task(
                self._shutdown_resources(retained), name="runtime-shutdown"
            )
        # A cancelled waiter must not abandon the resource holds or interrupt
        # channels halfway through cleanup. Later callers join the same exit.
        await asyncio.shield(self._shutdown_task)

    async def _shutdown_resources(self, retained: RuntimeRetention) -> None:
        try:
            await run_cleanup_steps(
                ("inbound.close", self._close_inbound),
                ("control_tasks.stop", self._stop_control_tasks),
                ("background.stop", self._stop_background),
                ("generations.drain", lambda: self._drain_generations(retained)),
                ("outbound.drain", self._drain_outbound),
                ("channels.stop", self._stop_channels),
                ("generations.release", retained.release),
                ("generations.close", self._close_generations),
                ("outbound.stop", self._stop_outbound),
                ("events.close", self._close_events),
                ("http_resources.aclose", self.http_resources.aclose),
                ("retired_runtime_cleanup", self._report_cleanup_errors),
                aggregate_errors=True,
            )
        finally:
            clear_default_shared_http_resources(self.http_resources)

    async def _drain_generations(self, retained: RuntimeRetention) -> None:
        if not self._generation_manager.tracked and self.core is not None:
            await self.core.drain()
            return
        await retained.drain()

    async def _close_inbound(self) -> None:
        if self.bus is not None:
            await self.bus.close_inbound()

    async def _stop_control_tasks(self) -> None:
        if self.agent_loop is not None:
            self.agent_loop.stop()
        if self.scheduler is not None:
            self.scheduler.stop()
        controls = [
            task
            for task in self._background_tasks
            if task.get_name() != "bus_dispatch_outbound"
        ]
        for task in controls:
            task.cancel()
        outcomes = await asyncio.gather(*controls, return_exceptions=True)
        self._cleanup_errors.extend(
            error for error in outcomes if isinstance(error, Exception)
        )
        self._background_tasks = [
            task for task in self._background_tasks if task not in controls
        ]

    async def _close_generations(self) -> None:
        if not self._generation_manager.tracked and self.core is not None:
            await run_cleanup_steps(
                ("partial_core.stop", lambda: self.core.stop(force=True)),
                ("partial_memory.close", self.core.memory_runtime.aclose),
                aggregate_errors=True,
            )
            return
        await self._generation_manager.close_all(force=True)

    async def _drain_outbound(self) -> None:
        if self.bus is not None:
            if self.bus.outbound_size and not any(
                not task.done() for task in self._background_tasks
            ):
                raise RuntimeError(
                    "Outbound dispatcher stopped before pending replies were delivered"
                )
            await self.bus.drain_outbound()

    async def _stop_channels(self) -> None:
        if self.channel_host is not None:
            await self.channel_host.stop_all()

    async def _stop_outbound(self) -> None:
        if self.bus is not None:
            self.bus.stop()
        for task in self._background_tasks:
            task.cancel()
        outcomes = await asyncio.gather(*self._background_tasks, return_exceptions=True)
        self._cleanup_errors.extend(
            error for error in outcomes if isinstance(error, Exception)
        )
        self._background_tasks = []

    async def _close_events(self) -> None:
        if self.event_bus is not None:
            await self.event_bus.aclose()

    async def _report_cleanup_errors(self) -> None:
        errors = [*self._cleanup_errors, *self._generation_manager.retirement_errors]
        if errors:
            raise ExceptionGroup("Retired runtime cleanup failed", errors)
