"""Keeps a run's danmaku stream connected, with bounded exponential backoff.

The login is re-validated before every (re)connection. Only transient
failures are retried (``failure_kind``); a rejection or an invalid login ends
the loop with ``LiveConnectionEnded``, and any other error propagates as is.
The backoff resets only after a connection stayed up for ``HEALTHY_AFTER_S``,
so a stream that drops right after connecting keeps backing off.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

from .bilibili_credentials import BilibiliCredentials
from .bilibili_danmaku import Danmaku
from .bilibili_live_stream import DanmakuSource, FailureKind, failure_kind
from .live_clock import Clock
from .live_status import ConnectionState, LiveCounter, LiveStatus

RECONNECT_BASE_S = 1.0
RECONNECT_MAX_S = 30.0
# A connection that lived this long counts as healthy and resets the backoff.
HEALTHY_AFTER_S = 30.0

logger = logging.getLogger(__name__)


class LiveConnectionEnded(RuntimeError):
    """Bilibili rejected the run or its login; ``state`` says which."""

    def __init__(self, state: ConnectionState, reason: str) -> None:
        super().__init__(reason)
        self.state = state


def reconnect_delay(failures: int) -> float:
    """Delay before the next attempt after ``failures`` consecutive failures."""
    return min(RECONNECT_BASE_S * 2 ** max(failures - 1, 0), RECONNECT_MAX_S)


class LiveConnection:
    """The stream sink of one run; forwards danmaku to ``on_danmaku``."""

    def __init__(
        self,
        *,
        room_id: int,
        buvid: str,
        credentials: Callable[[], Awaitable[BilibiliCredentials]],
        source: DanmakuSource,
        on_danmaku: Callable[[Danmaku], None],
        status: LiveStatus,
        clock: Clock,
    ) -> None:
        self._room_id = room_id
        self._buvid = buvid
        self._credentials = credentials
        self._source = source
        self._on_danmaku = on_danmaku
        self._status = status
        self._clock = clock
        self._connected_at: float | None = None

    async def run(self) -> None:
        """Connect and reconnect until cancelled or the stream is refused."""
        failures = 0
        while True:
            self._connected_at = None
            try:
                credentials = await self._credentials()
                await self._source.run(self._room_id, credentials, self._buvid, self)
            except Exception as error:
                kind = failure_kind(error)
                if kind is None:
                    raise
                if kind is not FailureKind.TRANSIENT:
                    state = (
                        ConnectionState.LOGIN_INVALID
                        if kind is FailureKind.LOGIN
                        else ConnectionState.REJECTED
                    )
                    self._status.connection_failed(state, str(error))
                    raise LiveConnectionEnded(state, str(error)) from error
                logger.warning("live danmaku connection lost: %r", error)
                message = f"弹幕连接中断: {error}"
                self._status.connection_failed(ConnectionState.RECONNECTING, message)
            failures = 1 if self._was_healthy() else failures + 1
            await self._clock.sleep(reconnect_delay(failures))

    def connected(self) -> None:
        """Auth accepted: the stream is live."""
        self._connected_at = self._clock.now()
        self._status.connected()

    def danmaku(self, message: Danmaku) -> None:
        """Forward a received danmaku (dedupe happens downstream)."""
        self._on_danmaku(message)

    def unreadable(self, error: str) -> None:
        """Count an unreadable ``DANMU_MSG``; the stream continues."""
        logger.warning("unreadable live danmaku: %s", error)
        self._status.count(LiveCounter.UNREADABLE)

    def _was_healthy(self) -> bool:
        started = self._connected_at
        return started is not None and self._clock.now() - started >= HEALTHY_AFTER_S
