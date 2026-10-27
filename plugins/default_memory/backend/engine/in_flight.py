"""Counts the engine calls in flight, so releasing the engine can wait for them."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager


class InFlightCalls:
    """The engine's async entry points that are running right now (D25).

    Host callers (passive retrieval, memory tools) and event-bus handlers
    reach the engine's async entry points outside the kernel's own drain.
    ``wait_idle`` lets the plugin's ``on_drain`` and the cleanup that closes the
    database wait for them instead of closing the store under a running call.
    Synchronous methods are not counted: they cannot interleave with the close
    on the event loop, so a caller only has to ``get`` the engine again after
    any ``await`` (``plugin_undo`` does).
    """

    def __init__(self) -> None:
        self._count = 0
        self._idle = asyncio.Event()
        self._idle.set()

    @asynccontextmanager
    async def track(self) -> AsyncGenerator[None]:
        """Marks one call in flight until the block exits."""
        self._count += 1
        self._idle.clear()
        try:
            yield
        finally:
            self._count -= 1
            if self._count == 0:
                self._idle.set()

    async def wait_idle(self) -> None:
        """Returns once no tracked call is running; only waits, never tears down."""
        _ = await self._idle.wait()
