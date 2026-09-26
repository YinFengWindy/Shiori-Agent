"""OneBot 11 forward WebSocket transport with correlated action receipts."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from typing import Any
from uuid import uuid4

from websockets.asyncio.client import connect


class OneBotError(RuntimeError):
    """A transport or platform action failed with a visible explanation."""


class OneBotAuthError(OneBotError):
    """NapCat is reachable but the configured QQ identity is not logged in."""


class OneBotSocket:
    """One isolated NapCat socket; no NcatBot process-global settings are used."""

    def __init__(
        self,
        uri: str,
        token: str,
        timeout_seconds: float,
        on_event: Callable[[dict[str, Any]], Awaitable[None]],
    ) -> None:
        self._uri = uri
        self._token = token
        self._timeout = timeout_seconds
        self._on_event = on_event
        self._socket: Any = None
        self._reader: asyncio.Task[None] | None = None
        self._events: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=256)
        self._event_worker: asyncio.Task[None] | None = None
        self._event_error: Exception | None = None
        self._pending: dict[str, asyncio.Future[dict[str, Any]]] = {}

    @property
    def closed(self) -> bool:
        """Whether the socket has stopped receiving replies."""
        return self._socket is None or self._reader is None or self._reader.done()

    async def open(self) -> None:
        """Opens the socket and starts the only reader for replies and events."""
        headers = {"Authorization": f"Bearer {self._token}"} if self._token else None
        self._socket = await connect(
            self._uri,
            additional_headers=headers,
            open_timeout=self._timeout,
        )
        self._event_worker = asyncio.create_task(
            self._dispatch_events(), name="qq-onebot-events"
        )
        self._reader = asyncio.create_task(self._read(), name="qq-onebot-reader")

    async def _dispatch_events(self) -> None:
        try:
            while True:
                await self._on_event(await self._events.get())
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self._event_error = exc
            socket = self._socket
            if socket is not None:
                await socket.close()

    async def _read(self) -> None:
        socket = self._socket
        try:
            async for raw in socket:
                payload = json.loads(raw)
                if not isinstance(payload, dict):
                    continue
                echo = payload.get("echo")
                if echo is not None:
                    future = self._pending.pop(str(echo), None)
                    if future is not None and not future.done():
                        future.set_result(payload)
                elif payload.get("post_type"):
                    try:
                        self._events.put_nowait(payload)
                    except asyncio.QueueFull as exc:
                        raise OneBotError("NapCat 事件队列已满") from exc
        finally:
            self._socket = None
            for future in self._pending.values():
                if not future.done():
                    future.set_exception(OneBotError("NapCat WebSocket 已断开"))
            self._pending.clear()
            try:
                await socket.close()
            finally:
                if self._event_worker is not None:
                    self._event_worker.cancel()
                    await asyncio.gather(self._event_worker, return_exceptions=True)
        if self._event_error is not None:
            raise OneBotError("NapCat 消息处理失败") from self._event_error

    async def call(self, action: str, params: dict[str, Any] | None = None) -> Any:
        """Checks OneBot status and retcode before returning actual API data."""
        if self.closed:
            raise OneBotError("NapCat WebSocket 未连接")
        echo = uuid4().hex
        future: asyncio.Future[dict[str, Any]] = (
            asyncio.get_running_loop().create_future()
        )
        self._pending[echo] = future
        try:
            await self._socket.send(
                json.dumps({"action": action, "params": params or {}, "echo": echo})
            )
            response = await asyncio.wait_for(future, timeout=self._timeout)
        finally:
            self._pending.pop(echo, None)
        if response.get("status") != "ok" or response.get("retcode") != 0:
            detail = response.get("wording") or response.get("message") or "未知错误"
            raise OneBotError(f"NapCat {action} 失败: {detail}")
        return response.get("data")

    async def wait_closed(self) -> None:
        """Waits for an unplanned socket close."""
        if self._reader is not None:
            await self._reader

    async def close(self) -> None:
        """Closes this one connection and settles its pending API requests."""
        socket = self._socket
        if socket is not None:
            await socket.close()
        if self._reader is not None:
            await asyncio.gather(self._reader, return_exceptions=True)
