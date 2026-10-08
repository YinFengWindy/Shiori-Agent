"""Supervision of a run's background tasks.

Tasks are spawned through the plugin's ``background`` capability, so plugin
cleanup reclaims them too. A task that fails (a bug, a protocol error) is
reported through ``on_failure`` instead of dying silently and leaving the run
hanging.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable, Coroutine
from typing import Protocol

logger = logging.getLogger(__name__)


class SpawnTask(Protocol):
    """``BackgroundTasks.spawn``: start a coroutine owned by the plugin."""

    def __call__(
        self, coro: Coroutine[object, object, None], *, name: str
    ) -> asyncio.Task[None]: ...


class TaskSupervisor:
    """Starts, cancels and watches the tasks of one run."""

    def __init__(
        self, spawn: SpawnTask, on_failure: Callable[[Exception], Awaitable[None]]
    ) -> None:
        self._spawn = spawn
        self._on_failure = on_failure
        self._tasks: list[asyncio.Task[None]] = []

    def start(
        self, work: Callable[[], Awaitable[None]], name: str
    ) -> asyncio.Task[None]:
        """Run ``work()`` in a supervised task."""
        task = self._spawn(self._guard(work), name=name)
        self._tasks.append(task)
        return task

    async def cancel(self, task: asyncio.Task[None]) -> None:
        """Cancel one task and wait for it, unless it is the calling task."""
        if task in self._tasks:
            self._tasks.remove(task)
        if task is not asyncio.current_task():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    async def cancel_all(self) -> None:
        """Cancel every task except the calling one and wait for them."""
        for task in list(self._tasks):
            await self.cancel(task)

    async def _guard(self, work: Callable[[], Awaitable[None]]) -> None:
        # ``work`` is created inside the task, so a task cancelled before it
        # first runs leaves no never-awaited coroutine behind.
        try:
            await work()
        except asyncio.CancelledError:
            raise
        except Exception as error:
            logger.exception("live run task failed")
            await self._on_failure(error)
