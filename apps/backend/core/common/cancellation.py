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


def raise_cancellation_again() -> None:
    """Make this task's next ``await`` raise the cancellation it just caught.

    For an operation that must report a result its caller acts on before a
    cancellation reaches that caller. A cancellation the task raised itself
    (none requested) becomes a requested one; a requested one keeps its count.
    """
    task = asyncio.current_task()
    if task is None:
        raise RuntimeError("raise_cancellation_again needs a running task")
    if task.cancelling():
        task.uncancel()
    task.cancel()
