from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

logger = logging.getLogger("desktop.bridge.dispatcher")

RequestOperation = Callable[[], Awaitable[None]]

_READ_ONLY_METHODS = frozenset(
    {
        "health",
        "roles.list",
        "roles.tasks.list",
        "novelai.history",
        "novelai.prompt_tags.list",
        "worlds.list",
        "worlds.get",
        "worlds.timeline",
        "worlds.events.catch_up",
    }
)
_INTEGRATION_METHODS = frozenset(
    {
        "novelai.generate",
        "worlds.drafts.preview",
    }
)
_BACKGROUND_WORLD_METHODS = frozenset(
    {
        "worlds.actions.submit",
        "worlds.advance",
        "worlds.barriers.resolve",
        "worlds.runs.cancel",
    }
)


class BridgeRequestDispatcher:
    """Runs bridge requests with bounded concurrency and one conservative write lane."""

    def __init__(
        self,
        *,
        max_concurrency: int = 8,
        integration_concurrency: int = 2,
    ) -> None:
        if max_concurrency < 1:
            raise ValueError("max_concurrency 必须大于 0")
        if integration_concurrency < 1:
            raise ValueError("integration_concurrency 必须大于 0")
        self._semaphore = asyncio.Semaphore(max_concurrency)
        self._integration_semaphore = asyncio.Semaphore(integration_concurrency)
        self._mutation_lock = asyncio.Lock()
        self._tasks: set[asyncio.Task[None]] = set()
        self._closed = False

    def submit(self, request: dict[str, Any], operation: RequestOperation) -> None:
        """Schedules one request without blocking the stream reader."""

        if self._closed:
            raise RuntimeError("bridge request dispatcher 已关闭")
        method = str(request.get("method") or "").strip()
        task = asyncio.create_task(
            self._run(method, operation),
            name=f"desktop-bridge:{method or 'invalid'}",
        )
        self._tasks.add(task)
        task.add_done_callback(self._on_task_done)

    async def aclose(self, *, cancel: bool = False) -> None:
        """Stops accepting work and awaits accepted requests, optionally cancelling them."""

        if self._closed:
            return
        self._closed = True
        tasks = list(self._tasks)
        if cancel:
            for task in tasks:
                if not task.done():
                    _ = task.cancel()
        if tasks:
            _ = await asyncio.gather(*tasks, return_exceptions=True)
        self._tasks.clear()

    async def _run(self, method: str, operation: RequestOperation) -> None:
        if method in _INTEGRATION_METHODS or method in _BACKGROUND_WORLD_METHODS:
            async with self._integration_semaphore:
                async with self._semaphore:
                    await operation()
            return
        if method in _READ_ONLY_METHODS:
            async with self._semaphore:
                await operation()
            return
        async with self._mutation_lock:
            async with self._semaphore:
                await operation()

    def _on_task_done(self, task: asyncio.Task[None]) -> None:
        self._tasks.discard(task)
        if task.cancelled():
            return
        try:
            error = task.exception()
        except asyncio.CancelledError:
            return
        if error is not None:
            logger.error(
                "desktop bridge request task failed",
                exc_info=(type(error), error, error.__traceback__),
            )
