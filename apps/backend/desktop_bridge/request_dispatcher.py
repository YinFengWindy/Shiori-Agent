from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from desktop_bridge.method_policy import Concurrency, MethodPolicy, method_policy

logger = logging.getLogger("desktop.bridge.dispatcher")

RequestOperation = Callable[[], Awaitable[None]]
PolicyResolver = Callable[[str], MethodPolicy]


class BridgeRequestDispatcher:
    """Runs bridge requests with bounded concurrency and one conservative write lane."""

    def __init__(
        self,
        *,
        max_concurrency: int = 8,
        integration_concurrency: int = 2,
        policy_resolver: PolicyResolver = method_policy,
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
        # 注入而非进程级全局字典：generation 相关的 plugin.* 方法策略随服务实例变化
        self._policy_resolver = policy_resolver

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
        lane = self._policy_resolver(method).concurrency
        if lane in (Concurrency.SETTINGS_APPLY, Concurrency.PLUGIN_TRANSPORT):
            # The runtime transaction owns its serial lock. Waiting for old work
            # must leave transport capacity for health, cancellation and rejection.
            await operation()
            return
        if lane is Concurrency.INTEGRATION:
            async with self._integration_semaphore:
                async with self._semaphore:
                    await operation()
            return
        if lane is Concurrency.READ_ONLY:
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
