"""Deterministic intake fake for testing transport admission without a host runtime."""

import asyncio
from collections import deque

from shiori_sdk.channels.services import InboundHandler, Sender
from shiori_sdk.messages import InboundMessage


class FakeChannelIntake:
    """Keep test-owned input queued until explicitly resumed or closed."""

    def __init__(self, accept: InboundHandler, send: Sender):
        self.accept = accept
        self.send = send
        self.pending: deque[InboundMessage] = deque()
        self.paused = False
        self.closed = False
        self.task: asyncio.Task[None] | None = None

    def start(self, *, paused: bool = False) -> None:
        """Reopen admission using the selected starting state."""
        self.closed = False
        self.paused = paused
        if not paused:
            self.resume()

    def pause(self) -> None:
        """Queue future input."""
        self.paused = True

    def resume(self) -> None:
        """Deliver queued input in order on the event loop."""
        self.paused = False
        if self.pending and (self.task is None or self.task.done()):
            self.task = asyncio.create_task(self._flush())

    async def _flush(self) -> None:
        while self.pending and not self.paused and not self.closed:
            await self.accept(self.pending.popleft())

    async def submit(self, message: InboundMessage) -> None:
        """Accept immediately or preserve the message for replay."""
        if self.closed:
            raise RuntimeError("Intake is closed")
        if self.paused or self.pending:
            self.pending.append(message)
            if not self.paused:
                self.resume()
        else:
            await self.accept(message)

    async def drain(self) -> None:
        """Wait for an already scheduled replay."""
        if self.task is not None:
            await self.task

    async def close(self) -> None:
        """Keep retry notices on the original transport before it disconnects."""
        self.closed = True
        self.pause()
        await self.drain()
        while self.pending:
            message = self.pending.popleft()
            await self.send(
                message.chat_id, "渠道配置正在切换，这条消息尚未处理，请稍后重新发送。"
            )
