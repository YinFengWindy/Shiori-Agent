"""Finish work that has already started before a caller's cancellation."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable


async def finish_started[T](
    operation: Awaitable[T], *, on_cancel: Callable[[], None] | None = None
) -> T:
    """Finish ``operation`` before propagating the caller's cancellation.

    ``on_cancel`` runs when the caller cancels, so the owner can withdraw
    work that has not started. A cancellation the operation itself raises
    still propagates at once.
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
