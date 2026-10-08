"""Time source of the live engine, injectable so tests control every wait."""

from __future__ import annotations

import asyncio
import time
from typing import Any, Protocol


class Clock(Protocol):
    """Monotonic seconds and sleeping measured on the same clock."""

    def now(self) -> float: ...

    async def sleep(self, seconds: float) -> None: ...


class SystemClock:
    """The real monotonic clock."""

    def now(self) -> float:
        """Monotonic seconds."""
        return time.monotonic()

    async def sleep(self, seconds: float) -> None:
        """Real asyncio sleep."""
        await asyncio.sleep(seconds)


class Wakeup:
    """A level-triggered signal a loop waits on, with an optional clock deadline."""

    def __init__(self, clock: Clock) -> None:
        self._clock = clock
        self._event = asyncio.Event()

    def set(self) -> None:
        """Wake the waiter now (or its next wait, if none is waiting)."""
        self._event.set()

    async def wait(self, timeout: float | None) -> None:
        """Return on ``set`` or after ``timeout`` clock seconds, then re-arm."""
        if not self._event.is_set():
            waits: list[asyncio.Future[Any]] = [
                asyncio.ensure_future(self._event.wait())
            ]
            if timeout is not None:
                waits.append(asyncio.ensure_future(self._clock.sleep(max(timeout, 0))))
            try:
                await asyncio.wait(waits, return_when=asyncio.FIRST_COMPLETED)
            finally:
                for task in waits:
                    task.cancel()
                await asyncio.gather(*waits, return_exceptions=True)
        self._event.clear()
