from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

WritePayload = Callable[[dict[str, Any]], Awaitable[None]]


@dataclass
class _QueuedPayload:
    payload: dict[str, Any]
    written: asyncio.Future[None]


class BridgeStreamWriter:
    """Serializes bridge frames through one backpressured writer task."""

    def __init__(self, write_payload: WritePayload, *, queue_size: int = 128) -> None:
        self._write_payload = write_payload
        self._queue: asyncio.Queue[_QueuedPayload | None] = asyncio.Queue(queue_size)
        self._task = asyncio.create_task(self._run(), name="desktop-bridge-writer")
        self._closed = False
        self._failure: BaseException | None = None

    async def write(self, payload: dict[str, Any]) -> None:
        """Queues one frame and waits until the underlying stream accepts it."""

        if self._failure is not None:
            raise RuntimeError("bridge writer 已失败") from self._failure
        if self._closed:
            raise RuntimeError("bridge writer 已关闭")
        written = asyncio.get_running_loop().create_future()
        await self._queue.put(_QueuedPayload(payload=payload, written=written))
        await written

    async def aclose(self) -> None:
        """Drains accepted frames and stops the writer task."""

        if self._closed:
            await self._task
            return
        self._closed = True
        await self._queue.put(None)
        await self._task

    async def _run(self) -> None:
        try:
            while True:
                item = await self._queue.get()
                try:
                    if item is None:
                        return
                    await self._write_payload(item.payload)
                    if not item.written.done():
                        item.written.set_result(None)
                except BaseException as error:
                    self._failure = error
                    if item is not None and not item.written.done():
                        item.written.set_exception(error)
                    self._fail_queued(error)
                    raise
                finally:
                    self._queue.task_done()
        finally:
            if self._failure is not None:
                self._fail_queued(self._failure)

    def _fail_queued(self, error: BaseException) -> None:
        while True:
            try:
                item = self._queue.get_nowait()
            except asyncio.QueueEmpty:
                return
            if item is not None and not item.written.done():
                item.written.set_exception(error)
            self._queue.task_done()
