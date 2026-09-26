"""Feishu long-connection (WebSocket) event subscription on a dedicated thread.

lark-oapi's ``ws.Client`` binds a module-global event loop at import time and
``start()`` blocks forever; stopping it needs private coroutines. Everything
touching those SDK internals lives in :class:`SdkLongConnection`, so an SDK
upgrade only has to be re-checked here (``tests/test_ws.py`` pins the private
surface). :class:`LongConnectionRunner` owns the thread, its private event
loop and reconnects; it never lets SDK work reach the host event loop.
"""

from __future__ import annotations

import asyncio
import importlib
import logging
import threading
from collections.abc import Awaitable, Callable, Coroutine
from dataclasses import dataclass
from typing import Any, Literal, Protocol

from .formatting import as_dict

logger = logging.getLogger(__name__)

EventCallback = Callable[[dict[str, Any]], None]
RECEIVE_EVENT = "im.message.receive_v1"
# Subscribed by many app templates; acknowledged without work so Feishu does
# not redeliver them as failures.
IGNORED_EVENTS = (
    "im.message.message_read_v1",
    "im.chat.access_event.bot_p2p_chat_entered_v1",
)
RECONNECT_DELAYS_S = (1.0, 2.0, 5.0, 10.0, 30.0, 60.0)
POLL_INTERVAL_S = 1.0
DISCONNECT_TIMEOUT_S = 5.0
JOIN_TIMEOUT_S = 10.0


class LongConnection(Protocol):
    """One long-connection session; created and used only on the runner thread."""

    async def connect(self) -> None: ...
    def is_connected(self) -> bool: ...
    async def keepalive(self) -> None: ...
    async def disconnect(self) -> None: ...


ConnectionFactory = Callable[[EventCallback], LongConnection]


@dataclass(frozen=True)
class ConnectionState:
    """Snapshot of the long connection for ``status()``."""

    connected: bool
    detail: str
    error_kind: Literal["auth", "capability", "transport"] | None = None


def classify_connection_error(
    error: BaseException,
) -> Literal["auth", "capability", "transport"]:
    """Maps SDK handshake and HTTP failures to account-facing causes."""
    code = getattr(error, "code", None)
    status = getattr(getattr(error, "response", None), "status_code", None)
    # SDK code 514 also covers connection-limit rejection; it discards the
    # handshake subcode, so only unambiguous credential errors require login.
    if code in {401, 10003, 10014, 1000040344} or status == 401:
        return "auth"
    if code == 403 or status == 403:
        return "capability"
    return "transport"


class _SdkLoopProxy:
    """Dispatches SDK module-global loop calls to the calling account thread."""

    def create_task(self, coro: Coroutine[Any, Any, Any]) -> asyncio.Task[Any]:
        return asyncio.get_running_loop().create_task(coro)

    def run_until_complete(self, awaitable: Awaitable[Any]) -> Any:
        # The plugin calls the SDK's async methods; retain its synchronous
        # Client.start() behavior for other users of the process-global module.
        return asyncio.get_event_loop().run_until_complete(awaitable)


_SDK_LOOP_PROXY = _SdkLoopProxy()


class SdkLongConnection:
    """Adapts lark-oapi's ``ws.Client`` to :class:`LongConnection`.

    Must be constructed on the runner thread while its loop runs: the SDK
    module holds a process-global ``loop`` reference. A loop proxy makes each
    SDK task follow its current runner thread without changing that global to
    another account's loop.
    """

    def __init__(
        self,
        app_id: str,
        app_secret: str,
        domain: str,
        on_event: EventCallback,
    ) -> None:
        client_module = importlib.import_module("lark_oapi.ws.client")
        client_module.loop = _SDK_LOOP_PROXY
        lark = importlib.import_module("lark_oapi")
        builder = lark.EventDispatcherHandler.builder("", "")
        builder.register_p2_customized_event(
            RECEIVE_EVENT, lambda event: on_event(_envelope(event))
        )
        for event_type in IGNORED_EVENTS:
            builder.register_p2_customized_event(event_type, lambda _event: None)
        self._client = client_module.Client(
            app_id,
            app_secret,
            log_level=lark.LogLevel.WARNING,
            event_handler=builder.build(),
            domain=domain,
            auto_reconnect=False,
        )

    async def connect(self) -> None:
        # Fetches the endpoint (blocking HTTP on this private loop) and starts
        # the SDK receive loop, which acks each frame after the handler returns.
        await self._client._connect()

    def is_connected(self) -> bool:
        return self._client._conn is not None

    async def keepalive(self) -> None:
        await self._client._ping_loop()

    async def disconnect(self) -> None:
        await self._client._disconnect()


def sdk_connection_factory(app_id: str, app_secret: str, domain: str):
    """Returns a factory building :class:`SdkLongConnection` for one app."""

    def factory(on_event: EventCallback) -> LongConnection:
        return SdkLongConnection(app_id, app_secret, domain, on_event)

    return factory


class LongConnectionRunner:
    """Runs one long connection with reconnects on a private thread and loop.

    ``on_event`` is invoked on the runner thread and must return quickly:
    Feishu expects the frame acknowledgement within 3 seconds and the SDK only
    acknowledges after the handler returns. ``stop`` is idempotent, waits for
    the thread to exit and never blocks the calling event loop.
    """

    def __init__(
        self,
        factory: ConnectionFactory,
        on_event: EventCallback,
        *,
        on_state: Callable[[ConnectionState], None] | None = None,
        name: str = "feishu-ws",
        reconnect_delays: tuple[float, ...] = RECONNECT_DELAYS_S,
        poll_interval: float = POLL_INTERVAL_S,
    ) -> None:
        self._factory = factory
        self._on_event = on_event
        self._on_state = on_state or (lambda _state: None)
        self._name = name
        self._reconnect_delays = reconnect_delays
        self._poll_interval = poll_interval
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._stop_requested = threading.Event()
        self._wakeup: asyncio.Event | None = None
        self._state = ConnectionState(False, "未连接")

    @property
    def state(self) -> ConnectionState:
        return self._state

    @property
    def alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> None:
        """Starts the thread. A runner is single-use; build a new one to restart.

        Single use keeps a slow-to-exit old thread (stuck in the SDK's blocking
        endpoint request) from ever sharing stop signals with a new one.
        """
        if self._thread is not None or self._stop_requested.is_set():
            raise RuntimeError("LongConnectionRunner 只能启动一次")
        self._set_state(False, "正在连接")
        self._thread = threading.Thread(target=self._run, name=self._name, daemon=True)
        self._thread.start()

    async def stop(self, timeout: float = JOIN_TIMEOUT_S) -> None:
        """Signals the thread and waits (off-loop) for it to exit."""
        self._stop_requested.set()
        self._wake()
        thread = self._thread
        if thread is None:
            return
        await asyncio.to_thread(thread.join, timeout)
        if thread.is_alive():
            logger.warning(
                "[feishu] 长连接线程 %.0fs 内未退出（可能卡在建连请求），"
                "已放弃等待；该守护线程不会阻止进程退出",
                timeout,
            )
            return
        self._set_state(False, "已停止")

    def _wake(self) -> None:
        loop, wakeup = self._loop, self._wakeup
        if loop is None or wakeup is None:
            return
        try:
            loop.call_soon_threadsafe(wakeup.set)
        except RuntimeError:
            pass  # the loop already closed

    def _set_state(
        self,
        connected: bool,
        detail: str,
        error_kind: Literal["auth", "capability", "transport"] | None = None,
    ) -> None:
        self._state = ConnectionState(connected, detail, error_kind)
        try:
            self._on_state(self._state)
        except Exception:
            logger.exception("[feishu] 连接状态回调失败")

    def _run(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.set_exception_handler(_log_loop_exception)
        try:
            self._wakeup = asyncio.Event()
            self._loop = loop
            if self._stop_requested.is_set():
                self._wakeup.set()
            loop.run_until_complete(self._supervise())
        except Exception:
            logger.exception("[feishu] 长连接线程异常退出")
        finally:
            self._loop = None
            _close_loop(loop)
            asyncio.set_event_loop(None)

    async def _supervise(self) -> None:
        failures = 0
        while not self._stop_requested.is_set():
            connection: LongConnection | None = None
            try:
                connection = self._factory(self._dispatch)
                await connection.connect()
            except Exception as error:
                logger.warning("[feishu] 长连接建立失败: %s", error)
                self._set_state(
                    False, f"连接失败：{error}", classify_connection_error(error)
                )
                if connection is not None:
                    await self._disconnect(connection)
                delay = self._delay(failures)
                failures += 1
                await self._sleep(delay)
                continue
            failures = 0
            self._set_state(True, "长连接已建立")
            logger.info("[feishu] 长连接已建立")
            keepalive = asyncio.create_task(connection.keepalive())
            try:
                while connection.is_connected() and not await self._sleep(
                    self._poll_interval
                ):
                    pass
            finally:
                keepalive.cancel()
                await asyncio.gather(keepalive, return_exceptions=True)
                await self._disconnect(connection)
            if not self._stop_requested.is_set():
                logger.warning("[feishu] 长连接断开，准备重连")
                self._set_state(False, "连接断开，正在重连")
                await self._sleep(self._delay(0))

    def _dispatch(self, envelope: dict[str, Any]) -> None:
        if self._stop_requested.is_set():
            return
        try:
            self._on_event(envelope)
        except Exception:
            # Raising would make the SDK answer 500 and Feishu redeliver.
            logger.exception("[feishu] 事件分发失败")

    def _delay(self, failures: int) -> float:
        return self._reconnect_delays[min(failures, len(self._reconnect_delays) - 1)]

    async def _sleep(self, seconds: float) -> bool:
        """Waits up to ``seconds``; returns True as soon as stop is requested."""
        wakeup = self._wakeup
        if wakeup is None or self._stop_requested.is_set():
            return True
        try:
            await asyncio.wait_for(wakeup.wait(), seconds)
        except TimeoutError:
            pass
        return self._stop_requested.is_set()

    @staticmethod
    async def _disconnect(connection: LongConnection) -> None:
        try:
            await asyncio.wait_for(connection.disconnect(), DISCONNECT_TIMEOUT_S)
        except Exception as error:
            logger.debug("[feishu] 断开长连接失败: %s", error)


def _envelope(event: Any) -> dict[str, Any]:
    header = getattr(event, "header", None)
    return {
        "header": {
            "event_id": str(getattr(header, "event_id", "") or ""),
            "event_type": str(getattr(header, "event_type", "") or ""),
        },
        "event": as_dict(getattr(event, "event", None)),
    }


def _log_loop_exception(
    loop: asyncio.AbstractEventLoop, context: dict[str, Any]
) -> None:
    # The SDK's receive task ends with an exception on every disconnect; that
    # is expected and handled by the supervisor's reconnect.
    logger.debug("[feishu] 长连接事件循环: %s", context.get("message"))


def _close_loop(loop: asyncio.AbstractEventLoop) -> None:
    """Cancels every task left by the SDK (receive, ping, cache cron) and closes."""
    try:
        pending = [task for task in asyncio.all_tasks(loop) if not task.done()]
        for task in pending:
            task.cancel()
        if pending:
            loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
        loop.run_until_complete(loop.shutdown_asyncgens())
    finally:
        loop.close()
