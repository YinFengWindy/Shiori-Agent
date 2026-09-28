"""Shared ownership of detached cleanup tasks and their deferred failures."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Coroutine

logger = logging.getLogger(__name__)


class TaskCollector:
    """Tracks fire-and-forget tasks so their failures surface at a lifecycle boundary."""

    def __init__(self, description: str) -> None:
        self._description = description
        self._tasks: set[asyncio.Task] = set()
        self._errors: list[Exception] = []

    @property
    def errors(self) -> list[Exception]:
        """Returns failures collected from completed tasks, oldest first."""
        return list(self._errors)

    def spawn(self, operation: Coroutine, *, name: str) -> asyncio.Task:
        """Schedules detached work whose failure is retained instead of lost."""
        task = asyncio.create_task(operation, name=name)
        self._tasks.add(task)
        task.add_done_callback(self._finished)
        return task

    def cancel_all(self) -> None:
        """Requests cancellation of every tracked task without waiting."""
        for task in self._tasks:
            task.cancel()

    async def drain(self) -> None:
        """Waits for tracked tasks; failures stay in `errors` rather than raising."""
        while self._tasks:
            await asyncio.gather(*list(self._tasks), return_exceptions=True)
            # Awaiting already-finished tasks does not yield, so give their
            # pending `_finished` callbacks a turn or this loop never ends.
            await asyncio.sleep(0)

    def _finished(self, task: asyncio.Task) -> None:
        self._tasks.discard(task)
        if task.cancelled():
            return
        error = task.exception()
        if isinstance(error, Exception):
            self._errors.append(error)
            logger.error(
                "%s failed: %s", self._description, task.get_name(), exc_info=error
            )
