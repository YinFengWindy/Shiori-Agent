"""Host-owned error attribution and process-wide hook lifetime contract."""

import asyncio
import logging
import threading
from collections.abc import Callable
from types import TracebackType
from typing import Protocol

SysExceptHook = Callable[
    [type[BaseException], BaseException, TracebackType | None], object
]
ThreadExceptHook = Callable[[threading.ExceptHookArgs], object]
LoopExceptHandler = Callable[[asyncio.AbstractEventLoop, dict[str, object]], object]


class Diagnostics(Protocol):
    """Connect a collector to the owning host without assuming an install layout."""

    def session_key(self) -> str | None: ...
    def top_frame(self, tb: TracebackType | None) -> str: ...
    def install_global_hooks(
        self,
        owner: object,
        handler: logging.Handler,
        system: SysExceptHook,
        thread: ThreadExceptHook,
        loop: asyncio.AbstractEventLoop | None,
        loop_handler: LoopExceptHandler,
    ) -> tuple[
        SysExceptHook | None, ThreadExceptHook | None, LoopExceptHandler | None
    ]: ...
    def uninstall_global_hooks(self, owner: object) -> None: ...
