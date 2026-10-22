"""What one plugin instance registered, and the fixed order it is released in (§8.4)."""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Awaitable, Callable, Coroutine, Generator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

from .contracts import plugin_logger

type Dispose = Callable[[], Awaitable[object] | object]

WATCH_GRACE = 1.0
"""Seconds a closing scope lets queued ``watch`` deliveries finish before cancelling."""


@dataclass(eq=False)
class _Entry:
    label: str
    dispose: Dispose
    subscription: bool


class Scope:
    """Subscriptions, tasks and effects of one plugin instance.

    ``close`` first stops admission and removes subscriptions, then drains
    ``watch`` workers briefly and cancels every task, then runs effects LIFO.
    A cleanup error is logged and collected; the rest still runs. When the
    caller cancels ``close``, entries not reached yet stay for a later call.
    """

    def __init__(self, owner: str) -> None:
        self.owner = owner
        self.drainers: list[Callable[[], Awaitable[None]]] = []
        self._closing = False
        self._entries: list[_Entry] = []
        self._tasks: set[asyncio.Task[Any]] = set()
        self._workers: set[asyncio.Task[Any]] = set()
        self._busy: set[asyncio.Future[None]] = set()
        self._lock = asyncio.Lock()

    @property
    def active(self) -> bool:
        """Whether the scope still admits registrations and handler calls."""
        return not self._closing

    @property
    def labels(self) -> list[str]:
        """Labels of the subscriptions and effects still held, in registration order."""
        return [entry.label for entry in self._entries]

    def ensure_active(self, label: str) -> None:
        """Rejects a registration before the caller acquires the resource behind it."""
        if self._closing:
            raise RuntimeError(f"插件 {self.owner} 的作用域已释放，拒绝登记: {label}")

    def effect(self, dispose: Dispose, label: str = "effect") -> Callable[[], None]:
        """Registers LIFO cleanup; returns an idempotent release of this registration."""
        return self._add(_Entry(label, dispose, subscription=False))

    def subscribe(self, cancel: Dispose, label: str = "subscription") -> None:
        """Registers a subscription removal, run before any task or effect."""
        _ = self._add(_Entry(label, cancel, subscription=True))

    def _add(self, entry: _Entry) -> Callable[[], None]:
        self.ensure_active(entry.label)
        self._entries.append(entry)

        def release() -> None:
            if entry in self._entries:
                self._entries.remove(entry)

        return release

    def spawn[T](
        self,
        coro: Coroutine[Any, Any, T],
        *,
        name: str | None = None,
        worker: bool = False,
    ) -> asyncio.Task[T]:
        """Runs ``coro`` as a task owned by this scope; ``close`` cancels it."""
        if self._closing:
            coro.close()
            self.ensure_active(f"task:{name}")
        task = asyncio.create_task(coro, name=name)
        (self._workers if worker else self._tasks).add(task)
        task.add_done_callback(self._finished)
        return task

    def _finished(self, task: asyncio.Task[Any]) -> None:
        self._tasks.discard(task)
        self._workers.discard(task)
        if not task.cancelled() and (error := task.exception()) is not None:
            log = plugin_logger(self.owner)
            log.error("插件 %s 的任务异常结束", self.owner, exc_info=error)

    @contextmanager
    def busy(self) -> Generator[None]:
        """Marks one handler call in flight, so a drain waits for it."""
        done: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        self._busy.add(done)
        try:
            yield
        finally:
            self._busy.discard(done)
            done.set_result(None)

    async def drain(self) -> None:
        """Default drain plus ``on_drain`` (D25).

        Waits for the ``on`` / ``watch`` handler calls in flight when the drain
        starts, then runs every registered ``on_drain`` callback in order.
        Spawned tasks are not waited for (a resident loop never ends); ``close``
        cancels them.
        """
        if self._busy:
            _ = await asyncio.wait(set(self._busy))
        for callback in list(self.drainers):
            await callback()

    async def close(self) -> list[Exception]:
        """Releases everything in the fixed order; returns the cleanup errors."""
        self._closing = True
        async with self._lock:
            errors: list[Exception] = []
            subscriptions = [e for e in reversed(self._entries) if e.subscription]
            for entry in subscriptions:
                await self._release(entry, errors)
            if self._workers:
                _ = await asyncio.wait(set(self._workers), timeout=WATCH_GRACE)
            tasks = {*self._tasks, *self._workers}
            for task in tasks:
                _ = task.cancel()
            _ = await asyncio.gather(*tasks, return_exceptions=True)
            while self._entries:
                await self._release(self._entries[-1], errors)
            self.drainers.clear()
            return errors

    async def _release(self, entry: _Entry, errors: list[Exception]) -> None:
        self._entries.remove(entry)
        try:
            result = entry.dispose()
            if inspect.isawaitable(result):
                await result
        except Exception as error:
            message = "插件 %s 清理 %s 失败: %s"
            plugin_logger(self.owner).warning(message, self.owner, entry.label, error)
            errors.append(error)
