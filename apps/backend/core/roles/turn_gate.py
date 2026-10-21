"""Role-owned gate leases that can yield during transport pacing."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from contextvars import ContextVar
from dataclasses import dataclass


@dataclass
class _GateLease:
    lock: asyncio.Lock
    held: bool = False

    async def acquire(self) -> None:
        await self.lock.acquire()
        self.held = True

    def release(self) -> None:
        if self.held:
            self.held = False
            self.lock.release()


_CURRENT_GATE: ContextVar[_GateLease | None] = ContextVar("role_gate", default=None)


@asynccontextmanager
async def role_turn_gate(lock: asyncio.Lock):
    """Own one acquisition, including cancellation while temporarily suspended."""
    lease = _GateLease(lock)
    await lease.acquire()
    token = _CURRENT_GATE.set(lease)
    try:
        yield
    finally:
        _CURRENT_GATE.reset(token)
        lease.release()


async def wait_outside_role_gate(wait: Callable[[], Awaitable[None]]) -> None:
    """Yield only a pure pacing wait; resume mutable work after reacquiring.

    If either the wait or reacquisition is cancelled, the original owner exits
    without releasing somebody else's lock. Generation, commit and channel
    acknowledgement never run in the suspended section.
    """
    lease = _CURRENT_GATE.get()
    if lease is None:
        await wait()
        return
    lease.release()
    await wait()
    await lease.acquire()
