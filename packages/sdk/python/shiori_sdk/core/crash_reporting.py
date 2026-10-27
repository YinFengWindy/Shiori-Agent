"""``CRASH_REPORTING``: the core service arbitrating process-wide crash hooks (D13b).

``sys.excepthook``, ``threading.excepthook`` and an event loop's exception
handler are process globals. Collectors register through this one service
instead of rewriting them directly, so overlapping plugin generations hand the
hooks over in order and the last one out restores the originals.

``session_key`` and ``top_frame`` are part of the same protocol (maintainer,
2026-10-27). The collector attributes a crash after it injects this key;
they are not a second key, and the ``diagnostics`` capability is gone.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from collections.abc import Callable
from types import TracebackType
from typing import Protocol

from shiori_sdk.kernel import Key

SysExceptHook = Callable[
    [type[BaseException], BaseException, TracebackType | None], object
]
ThreadExceptHook = Callable[[threading.ExceptHookArgs], object]
LoopExceptHandler = Callable[[asyncio.AbstractEventLoop, dict[str, object]], object]


class CrashReporting(Protocol):
    """Installs one active crash collector at a time, stacked by ``owner``."""

    def install(
        self,
        owner: object,
        handler: logging.Handler,
        system: SysExceptHook,
        thread: ThreadExceptHook,
        loop: asyncio.AbstractEventLoop | None,
        loop_handler: LoopExceptHandler,
    ) -> tuple[SysExceptHook | None, ThreadExceptHook | None, LoopExceptHandler | None]:
        """Makes ``owner`` the active collector; returns the original hooks.

        The originals are the hooks in place before any collector, so the
        collector can chain to them.
        """
        ...

    def uninstall(self, owner: object) -> None:
        """Retires ``owner``; the previous collector or the originals take over."""
        ...

    def session_key(self) -> str | None:
        """The host's current passive-turn attribution, if a turn is in progress."""
        ...

    def top_frame(self, tb: TracebackType | None) -> str:
        """The first frame the host or a plugin owns, else the innermost filename."""
        ...


CRASH_REPORTING: Key[CrashReporting] = Key("crash_reporting")
"""Host core service. Observe injects it and registers its collector through it."""
