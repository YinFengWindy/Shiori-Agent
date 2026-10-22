"""``CRASH_REPORTING``: the core service arbitrating process-wide crash hooks (D13b).

``sys.excepthook``, ``threading.excepthook`` and an event loop's exception
handler are process globals. Collectors register through this one service
instead of rewriting them directly, so overlapping plugin generations hand the
hooks over in order and the last one out restores the originals.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Protocol

from shiori_sdk.diagnostics import LoopExceptHandler, SysExceptHook, ThreadExceptHook
from shiori_sdk.kernel import Key


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


CRASH_REPORTING: Key[CrashReporting] = Key("crash_reporting")
"""Provided by the host's core diagnostics module; observe injects it (P3)."""
