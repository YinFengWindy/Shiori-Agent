"""Process-wide crash hooks and crash-report attribution (``CRASH_REPORTING``, D13b).

Exception hooks are owned across overlapping plugin generations by one stack;
attribution uses explicit installed-code roots.
"""

from __future__ import annotations

import asyncio
import logging
import sys
import threading
import traceback
from collections.abc import Sequence
from dataclasses import dataclass
from importlib.util import find_spec
from pathlib import Path
from types import TracebackType

from core.error_context import current_session_key
from shiori_sdk.core.crash_reporting import (
    LoopExceptHandler,
    SysExceptHook,
    ThreadExceptHook,
)


@dataclass
class _Hooks:
    owner: object
    handler: logging.Handler
    system: SysExceptHook
    thread: ThreadExceptHook
    loop: asyncio.AbstractEventLoop | None
    loop_handler: LoopExceptHandler


_owners: list[_Hooks] = []
_original_system: SysExceptHook | None = None
_original_thread: ThreadExceptHook | None = None
_original_loop_handlers: dict[asyncio.AbstractEventLoop, LoopExceptHandler | None] = {}


def _install_global_hooks(
    owner: object,
    handler: logging.Handler,
    system: SysExceptHook,
    thread: ThreadExceptHook,
    loop: asyncio.AbstractEventLoop | None,
    loop_handler: LoopExceptHandler,
) -> tuple[SysExceptHook | None, ThreadExceptHook | None, LoopExceptHandler | None]:
    """Installs one active collector, returning the original non-collector hooks."""
    global _original_system, _original_thread
    if not _owners:
        _original_system = sys.excepthook
        _original_thread = threading.excepthook
    else:
        logging.getLogger().removeHandler(_owners[-1].handler)
    if loop is not None and loop not in _original_loop_handlers:
        _original_loop_handlers[loop] = loop.get_exception_handler()
    hooks = _Hooks(owner, handler, system, thread, loop, loop_handler)
    _owners.append(hooks)
    logging.getLogger().addHandler(handler)
    sys.excepthook = system
    threading.excepthook = thread
    if loop is not None:
        loop.set_exception_handler(loop_handler)
    return (
        _original_system,
        _original_thread,
        (_original_loop_handlers.get(loop) if loop is not None else None),
    )


def _uninstall_global_hooks(owner: object) -> None:
    """Removes any retired owner without restoring another retired collector."""
    index = next(
        (index for index, item in enumerate(_owners) if item.owner is owner), None
    )
    if index is None:
        return
    hooks = _owners.pop(index)
    logging.getLogger().removeHandler(hooks.handler)
    if index == len(_owners):
        previous = _owners[-1] if _owners else None
        if previous is not None:
            logging.getLogger().addHandler(previous.handler)
        if sys.excepthook == hooks.system and _original_system is not None:
            sys.excepthook = previous.system if previous else _original_system
        if threading.excepthook == hooks.thread and _original_thread is not None:
            threading.excepthook = previous.thread if previous else _original_thread
        if hooks.loop is not None and not hooks.loop.is_closed():
            if hooks.loop.get_exception_handler() == hooks.loop_handler:
                hooks.loop.set_exception_handler(
                    previous.loop_handler
                    if previous and previous.loop is hooks.loop
                    else _original_loop_handlers.get(hooks.loop)
                )
    if not _owners:
        _original_loop_handlers.clear()


class HostCrashReporting:
    """``CRASH_REPORTING``: the process hook stack plus session and frame attribution.

    Every instance shares the module-level hook stack above, because the hooks
    it arbitrates are process globals; only the attribution roots are per
    instance.
    """

    def __init__(self, plugin_roots: Sequence[tuple[str, Path]] = ()) -> None:
        self._roots = list(plugin_roots)
        # Package locations remain valid in a source tree, wheel or frozen layout.
        for name in (
            "agent",
            "bootstrap",
            "bus",
            "conversation",
            "core",
            "desktop_bridge",
            "infra",
            "proactive_v2",
            "prompts",
            "session",
            "utils",
            "shiori_runtime_resources",
        ):
            spec = find_spec(name)
            if spec is not None and spec.submodule_search_locations is not None:
                self._roots.extend(
                    (name, Path(path).resolve())
                    for path in spec.submodule_search_locations
                )

    def session_key(self) -> str | None:
        """Read the host's current passive-turn error attribution."""
        return current_session_key.get()

    def top_frame(self, tb: TracebackType | None) -> str:
        """Prefer the first owned frame; otherwise report the innermost filename."""
        frames = traceback.extract_tb(tb) if tb else []
        for frame in frames:
            for label, root in self._roots:
                path = Path(frame.filename).resolve()
                if path.is_relative_to(root):
                    return f"{label}/{path.relative_to(root).as_posix()}:{frame.lineno or 0}"
        return (
            f"{Path(frames[-1].filename).name}:{frames[-1].lineno or 0}"
            if frames
            else "?"
        )

    install = staticmethod(_install_global_hooks)
    uninstall = staticmethod(_uninstall_global_hooks)
