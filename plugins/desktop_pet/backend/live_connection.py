"""Keeps a run's danmaku stream connected, with bounded exponential backoff.

The login is re-validated before every (re)connection; a login Bilibili
rejects, or a stream that delivers anonymized senders, ends the loop by
raising instead of silently receiving as an anonymous visitor.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

from .bilibili_credentials import BilibiliCredentials
from .bilibili_danmaku import Danmaku
from .bilibili_live_source import DanmakuSource, LiveIdentityRejected
from .bilibili_login import BilibiliLoginRequired
from .live_clock import Clock
from .live_status import ConnectionState, LiveStatus

RECONNECT_BASE_S = 1.0
RECONNECT_MAX_S = 30.0

logger = logging.getLogger(__name__)


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
        self._connected = False

    async def run(self) -> None:
        """Connect and reconnect until cancelled or the login becomes invalid."""
        failures = 0
        while True:
            self._connected = False
            try:
                credentials = await self._credentials()
                await self._source.run(self._room_id, credentials, self._buvid, self)
            except (BilibiliLoginRequired, LiveIdentityRejected) as error:
                self._status.connection = ConnectionState.LOGIN_INVALID
                self._status.fail(str(error))
                raise
            except Exception as error:  # every other stream failure reconnects
                logger.warning("live danmaku connection lost: %r", error)
                self._status.fail(f"弹幕连接中断: {error}")
            failures = 1 if self._connected else failures + 1
            self._status.connection = ConnectionState.RECONNECTING
            await self._clock.sleep(reconnect_delay(failures))

    def connected(self) -> None:
        """Auth accepted: the stream is live."""
        self._connected = True
        self._status.connection = ConnectionState.CONNECTED

    def danmaku(self, message: Danmaku) -> None:
        """Forward a received danmaku (dedupe happens downstream)."""
        self._on_danmaku(message)

    def unreadable(self, error: str) -> None:
        """Count and show an unreadable ``DANMU_MSG``; the stream continues."""
        self._status.count("unreadable")
        self._status.fail(error)
