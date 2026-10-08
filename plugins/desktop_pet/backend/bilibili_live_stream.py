"""Contract of a danmaku stream connection: interfaces and failure kinds.

A source runs one connection and always ends by raising. What it raises
decides what the run does next (see ``failure_kind``):

- transient — network or transport trouble, or a server-side 5xx: reconnect
  with backoff;
- rejected — Bilibili refused the room, the stream or its request (business
  error codes such as -352 risk control, HTTP 4xx, auth reply ≠ 0): the run
  ends with that reason instead of retrying forever;
- login — the login is invalid or the stream delivers anonymized senders: the
  run ends and never degrades to anonymous receiving;
- anything else (protocol format errors, bugs) is not classified and ends the
  run as an error.
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from enum import StrEnum
from typing import Protocol

import httpx
from websockets.exceptions import ConnectionClosed, InvalidStatus

from .bilibili_api import BilibiliApiError
from .bilibili_credentials import BilibiliCredentials
from .bilibili_danmaku import Danmaku
from .bilibili_login import BilibiliLoginRequired


class LiveDisconnected(ConnectionError):
    """The stream ended or went silent; reconnecting may recover."""


class LiveAuthRejected(RuntimeError):
    """The server refused the auth packet of a freshly issued token."""


class LiveIdentityRejected(RuntimeError):
    """Danmaku arrive anonymized: the stream is not using the login identity."""


class FailureKind(StrEnum):
    """How a run reacts to a connection failure."""

    TRANSIENT = "transient"
    REJECTED = "rejected"
    LOGIN = "login"


def failure_kind(error: BaseException) -> FailureKind | None:
    """Classify a connection failure; ``None`` means a bug or protocol error."""
    if isinstance(error, (BilibiliLoginRequired, LiveIdentityRejected)):
        return FailureKind.LOGIN
    if isinstance(error, (LiveAuthRejected, BilibiliApiError)):
        return FailureKind.REJECTED
    if isinstance(error, httpx.HTTPStatusError):
        server_side = error.response.status_code >= 500
        return FailureKind.TRANSIENT if server_side else FailureKind.REJECTED
    if isinstance(error, InvalidStatus):
        server_side = error.response.status_code >= 500
        return FailureKind.TRANSIENT if server_side else FailureKind.REJECTED
    if isinstance(error, (httpx.TransportError, ConnectionClosed, OSError)):
        # OSError covers socket errors, TimeoutError and LiveDisconnected.
        return FailureKind.TRANSIENT
    return None


class LiveSocket(Protocol):
    """The subset of a websocket client connection the stream uses."""

    async def send(self, message: bytes) -> None: ...

    async def recv(self) -> str | bytes: ...


# Opens one websocket for a ``wss://`` URL; injectable for tests.
type SocketConnector = Callable[[str], AbstractAsyncContextManager[LiveSocket]]


class DanmakuSink(Protocol):
    """Receives what one connection observes, in order."""

    def connected(self) -> None:
        """The server accepted the auth packet."""
        ...

    def danmaku(self, message: Danmaku) -> None:
        """A plain-text viewer danmaku arrived (possibly a replay)."""
        ...

    def unreadable(self, error: str) -> None:
        """A ``DANMU_MSG`` could not be read; the connection continues."""
        ...


class DanmakuSource(Protocol):
    """Runs one connection; injectable so tests drive a controllable source."""

    async def run(
        self,
        room_id: int,
        credentials: BilibiliCredentials,
        buvid: str,
        sink: DanmakuSink,
    ) -> None:
        """Stream until the connection fails; always ends by raising."""
        ...
