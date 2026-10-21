"""Cancellation boundaries for operations that must finish once started."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable


async def finish_started[T](
    operation: Awaitable[T], *, on_cancel: Callable[[], None] | None = None
) -> T:
    """Finish one started operation before propagating caller cancellation.

    Repeated cancellation cannot abandon the operation. ``on_cancel`` lets its
    owner withdraw work that has not started yet; cancellation raised by the
    operation itself still propagates immediately. Callers own timeout bounds.
    """
    task = asyncio.ensure_future(operation)
    cancelled = False
    while True:
        try:
            result = await asyncio.shield(task)
            break
        except asyncio.CancelledError:
            if on_cancel is not None:
                on_cancel()
            if task.cancelled():
                raise
            cancelled = True
    if cancelled:
        raise asyncio.CancelledError
    return result
