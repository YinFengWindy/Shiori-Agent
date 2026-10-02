"""The single transport consumer selects a configuration for each new task."""

from __future__ import annotations

from typing import TYPE_CHECKING

from bootstrap.runtime.generations import RuntimeLease

from core.common.runtime_scope import bind_runtime, current_runtime_lease

if TYPE_CHECKING:
    from bootstrap.app import AppRuntime


class RuntimeDispatcher:
    """Routes scheduled and channel work while retaining generation ownership."""

    def __init__(self, app: AppRuntime) -> None:
        self._app = app

    async def run(self) -> None:
        """Consumes each channel message once and pins its selected runtime."""
        while True:
            item = await self._app.bus.consume_inbound()
            inherited = item.runtime_lease
            if inherited is not None and not isinstance(inherited, RuntimeLease):
                raise TypeError(
                    "Inbound runtime ownership must be supplied by the host"
                )
            if inherited is None:
                await self._app.wait_for_admission()
            async with inherited or self._app.acquire() as lease:
                with bind_runtime(lease):
                    await lease.core.loop.process_inbound(item)

    async def process_direct(self, *args, **kwargs):
        """Keeps scheduled child turns on their parent operation's runtime."""
        current = current_runtime_lease()
        if current is not None:
            return await current.core.loop.process_direct(*args, **kwargs)
        await self._app.wait_for_admission()
        async with self._app.acquire() as lease:
            with bind_runtime(lease):
                return await lease.core.loop.process_direct(*args, **kwargs)

    async def run_role_operation(self, metadata, operation):
        """Pins the complete scheduled operation, including its child turns."""
        await self._app.wait_for_admission()
        async with self._app.acquire() as lease:
            with bind_runtime(lease):
                return await lease.core.loop.run_role_operation(metadata, operation)

    def request_interrupt(
        self, session_key: str, sender: str = "", command: str = "/stop"
    ):
        """Cancels the original task through the shared interrupt registry."""
        return self._app.agent_loop.request_interrupt(session_key, sender, command)

    def discard_interrupt_state(self, session_key, state):
        """Removes a durably saved interrupt snapshot from shared state."""
        self._app.agent_loop.discard_interrupt_state(session_key, state)
