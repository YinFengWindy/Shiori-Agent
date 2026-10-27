"""Crash-report attribution with explicit installed-code roots."""

import asyncio
import logging
import traceback
from collections.abc import Sequence
from importlib.util import find_spec
from pathlib import Path
from types import TracebackType

from core.common.global_hook_stack import ProcessCrashReporting
from core.error_context import current_session_key
from shiori_sdk.core.crash_reporting import (
    LoopExceptHandler,
    SysExceptHook,
    ThreadExceptHook,
)


class HostCrashReporting:
    """``CRASH_REPORTING``: the process hook stack plus session and frame attribution."""

    def __init__(
        self,
        crash_reporting: ProcessCrashReporting,
        plugin_roots: Sequence[tuple[str, Path]] = (),
    ) -> None:
        self._crash_reporting = crash_reporting
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

    def install(
        self,
        owner: object,
        handler: logging.Handler,
        system: SysExceptHook,
        thread: ThreadExceptHook,
        loop: asyncio.AbstractEventLoop | None,
        loop_handler: LoopExceptHandler,
    ) -> tuple[SysExceptHook | None, ThreadExceptHook | None, LoopExceptHandler | None]:
        """Installs the collector on the process-wide hook stack."""
        return self._crash_reporting.install(
            owner, handler, system, thread, loop, loop_handler
        )

    def uninstall(self, owner: object) -> None:
        """Retires the collector on the process-wide hook stack."""
        self._crash_reporting.uninstall(owner)
