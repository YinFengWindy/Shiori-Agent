"""Deterministic intake fake for testing transport admission without a host runtime."""

import asyncio
import logging
from collections import deque
from contextvars import Context

from shiori_sdk.channels.services import (
    CHANNEL_INTAKE_CAPACITY,
    CHANNEL_INTAKE_RETRY_NOTICE,
    InboundHandler,
    Sender,
)
from shiori_sdk.messages import InboundMessage

logger = logging.getLogger(__name__)


class FakeChannelIntake:
    """Follow the host intake's closed, overflow and failed-replay replies in-process.

    Like the host, rejected input is answered with ``CHANNEL_INTAKE_RETRY_NOTICE``
    on the original sender, and replay failures are recorded and reported by
    ``drain()`` / ``close()`` as an ``ExceptionGroup``.
    """

    def __init__(
        self,
        accept: InboundHandler,
        send: Sender,
        *,
        capacity: int = CHANNEL_INTAKE_CAPACITY,
    ):
        if capacity < 1:
            raise ValueError("Channel intake capacity must be positive")
        self.accept = accept
        self.send = send
        self.capacity = capacity
        self.pending: deque[InboundMessage] = deque()
        self.paused = False
        self.closed = False
        self.task: asyncio.Task[None] | None = None
        self.errors: list[Exception] = []

    def start(self, *, paused: bool = False) -> None:
        """Reopen admission using the selected starting state."""
        self.closed = False
        if paused:
            self.pause()
        else:
            self.resume()

    def pause(self) -> None:
        """Queue future input."""
        self.paused = True

    def resume(self) -> None:
        """Deliver queued input in order once the current publication finishes."""
        self.paused = False
        if not self.closed and self.pending and (self.task is None or self.task.done()):
            # A fresh context keeps replay from inheriting the caller's state.
            self.task = asyncio.create_task(self._flush(), context=Context())

    async def _flush(self) -> None:
        while self.pending and not self.paused and not self.closed:
            message = self.pending.popleft()
            try:
                await self.accept(message)
            except Exception as error:
                # Like the host: record, answer the sender, and report on drain().
                self.errors.append(error)
                logger.exception("Buffered channel input could not be accepted")
                try:
                    await self._reject(message)
                except Exception as notice_error:
                    self.errors.append(notice_error)
                    logger.exception("Channel retry notice could not be delivered")

    async def _reject(self, message: InboundMessage) -> None:
        _ = await self.send(message.chat_id, CHANNEL_INTAKE_RETRY_NOTICE)

    async def submit(self, message: InboundMessage) -> None:
        """Accept, buffer during a pause, or reply with a notice when closed or full."""
        if self.closed or len(self.pending) >= self.capacity:
            await self._reject(message)
        elif self.paused or self.pending:
            self.pending.append(message)
            if not self.paused:
                self.resume()
        else:
            await self.accept(message)

    async def drain(self) -> None:
        """Wait for scheduled replay and report any recorded failure."""
        if self.task is not None:
            await asyncio.shield(self.task)
        if self.errors:
            errors, self.errors = self.errors, []
            raise ExceptionGroup("Channel intake failed", errors)

    async def close(self) -> None:
        """Keep retry notices on the original transport before it disconnects."""
        self.closed = True
        self.pause()
        if self.task is not None:
            await asyncio.shield(self.task)
        while self.pending:
            try:
                await self._reject(self.pending.popleft())
            except Exception as error:
                self.errors.append(error)
        await self.drain()
