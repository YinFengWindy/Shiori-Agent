"""Recording diagnostic ports; never installs process-wide exception hooks."""

import asyncio
import logging
from contextvars import ContextVar
from dataclasses import dataclass
from types import TracebackType
from shiori_sdk.diagnostics import SysExceptHook, ThreadExceptHook, LoopExceptHandler


@dataclass(frozen=True)
class _Generation:
    owner: object
    handler: logging.Handler
    system: SysExceptHook
    thread: ThreadExceptHook
    loop: asyncio.AbstractEventLoop | None
    loop_handler: LoopExceptHandler


class FakeDiagnostics:
    """Expose callbacks so tests can drive error sources without touching host globals."""

    def __init__(self):
        self.current_session: ContextVar[str | None] = ContextVar(
            "fake_session", default=None
        )
        self.handler: logging.Handler | None = None
        self.system: SysExceptHook | None = None
        self.thread: ThreadExceptHook | None = None
        self.loop_handler: LoopExceptHandler | None = None
        self.owners: list[object] = []
        self._generations: list[_Generation] = []
        self.frame = "test.py:1"

    def session_key(self) -> str | None:
        """Return test-local context attribution."""
        return self.current_session.get()

    def top_frame(self, tb: TracebackType | None) -> str:
        """Return the controlled attribution chosen by the test."""
        return self.frame

    def install_global_hooks(
        self,
        owner: object,
        handler: logging.Handler,
        system: SysExceptHook,
        thread: ThreadExceptHook,
        loop: asyncio.AbstractEventLoop | None,
        loop_handler: LoopExceptHandler,
    ) -> tuple[SysExceptHook | None, ThreadExceptHook | None, LoopExceptHandler | None]:
        """Record the callbacks without taking process-global ownership.

        Like the host, the newest live owner's callbacks are the active ones.
        """
        self._generations.append(
            _Generation(owner, handler, system, thread, loop, loop_handler)
        )
        self.owners.append(owner)
        self.handler, self.system, self.thread, self.loop_handler = (
            handler,
            system,
            thread,
            loop_handler,
        )
        return None, None, None

    def uninstall_global_hooks(self, owner: object) -> None:
        """Remove one registration of ``owner``, mirroring the host hook stack.

        Only the oldest matching registration is removed. Retiring the newest
        generation falls back to the previous owner's callbacks; its loop
        handler is restored only when both generations share the same loop,
        otherwise the loop's original (``None``) handler is reinstated.
        """
        index = next(
            (i for i, item in enumerate(self._generations) if item.owner is owner),
            None,
        )
        if index is None:
            return
        removed = self._generations.pop(index)
        self.owners.pop(index)
        if index != len(self._generations):
            return
        if not self._generations:
            self.handler = self.system = self.thread = self.loop_handler = None
            return
        previous = self._generations[-1]
        self.handler, self.system, self.thread = (
            previous.handler,
            previous.system,
            previous.thread,
        )
        self.loop_handler = (
            previous.loop_handler if previous.loop is removed.loop else None
        )
