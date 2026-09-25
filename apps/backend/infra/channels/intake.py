"""Bounded admission buffering shared by transports during configuration changes."""

from __future__ import annotations

import asyncio
import logging
from collections import deque
from collections.abc import Awaitable, Callable
from contextvars import Context

from bus.events import InboundMessage

logger = logging.getLogger(__name__)
_RETRY_MESSAGE = "渠道配置正在切换，这条消息尚未处理，请稍后重新发送。"


class ChannelIntake:
    """Buffers unaccepted input and keeps retry notices on its original transport."""

    def __init__(
        self,
        accept: Callable[[InboundMessage], Awaitable[None]],
        # Senders may return a platform message id; notices ignore it.
        send: Callable[[str, str], Awaitable[str | None]],
        *,
        capacity: int = 256,
    ) -> None:
        if capacity < 1:
            raise ValueError("Channel intake capacity must be positive")
        self._accept = accept
        self._send = send
        self._capacity = capacity
        self._pending: deque[InboundMessage] = deque()
        self._paused = False
        self._closed = False
        self._flush_task: asyncio.Task[None] | None = None
        self._errors: list[Exception] = []

    def start(self, *, paused: bool = False) -> None:
        """Reopens a stopped connection without carrying input across identities."""
        self._closed = False
        if paused:
            self.pause()
        else:
            self.resume()

    def pause(self) -> None:
        """Defers admission while keeping a bounded queue of received messages."""
        self._paused = True

    def resume(self) -> None:
        """Schedules buffered messages after the synchronous publication finishes."""
        self._paused = False
        if (
            not self._closed
            and self._pending
            and (self._flush_task is None or self._flush_task.done())
        ):
            self._flush_task = asyncio.create_task(self._flush(), context=Context())

    async def submit(self, message: InboundMessage) -> None:
        """Accepts input, buffers it during a pause, or replies explicitly on overflow."""
        if self._closed or len(self._pending) >= self._capacity:
            await self._reject(message)
        elif self._paused or self._pending:
            self._pending.append(message)
            if not self._paused:
                self.resume()
        else:
            await self._accept(message)

    async def _flush(self) -> None:
        while self._pending and not self._paused and not self._closed:
            message = self._pending.popleft()
            try:
                await self._accept(message)
            except Exception as error:
                self._errors.append(error)
                logger.exception("Buffered channel input could not be accepted")
                try:
                    await self._reject(message)
                except Exception as notice_error:
                    self._errors.append(notice_error)
                    logger.exception("Channel retry notice could not be delivered")

    async def _reject(self, message: InboundMessage) -> None:
        _ = await self._send(message.chat_id, _RETRY_MESSAGE)

    async def drain(self) -> None:
        """Waits for scheduled admission and reports any asynchronous failure."""
        if self._flush_task is not None:
            await asyncio.shield(self._flush_task)
        if self._errors:
            errors, self._errors = self._errors, []
            raise ExceptionGroup("Channel intake failed", errors)

    async def close(self) -> None:
        """Replies to buffered input before the original sender is disconnected."""
        self._closed = True
        self.pause()
        if self._flush_task is not None:
            await asyncio.shield(self._flush_task)
        while self._pending:
            try:
                await self._reject(self._pending.popleft())
            except Exception as error:
                self._errors.append(error)
        await self.drain()
