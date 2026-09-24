"""Owns the NcatBot receive loop separately from its process-global configuration."""

from __future__ import annotations

import asyncio
from concurrent.futures import Future


class QQSdkRuntime:
    """Stops the SDK receive loop before unloading plugins or replacing credentials."""

    def __init__(self, bot) -> None:
        self.bot = bot
        self._receive_task: asyncio.Task | None = None
        self._receive_finished: Future[None] = Future()
        self._stopping = False
        connect = bot.adapter.connect_websocket

        async def receive():
            self._receive_task = asyncio.current_task()
            try:
                return await connect()
            except asyncio.CancelledError:
                if not self._stopping:
                    raise
                # NcatBot's backend thread does not handle CancelledError. Its
                # adapter has already closed the socket in cancellation cleanup.
                return False
            finally:
                self._receive_finished.set_result(None)

        bot.adapter.connect_websocket = receive

    async def stop(self) -> None:
        """Waits for socket cleanup; bot_exit alone leaves the receive loop alive."""
        self._stopping = True
        task = self._receive_task
        if task is not None:
            if not task.done():
                task.get_loop().call_soon_threadsafe(task.cancel)
            await asyncio.wrap_future(self._receive_finished)
        await asyncio.to_thread(self.bot.bot_exit)
