"""Recording diagnostic ports; never installs process-wide exception hooks."""

import asyncio
import logging
from contextvars import ContextVar
from types import TracebackType
from shiori_sdk.diagnostics import SysExceptHook, ThreadExceptHook, LoopExceptHandler


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
        """Record the callbacks without taking process-global ownership."""
        self.owners.append(owner)
        self.handler, self.system, self.thread, self.loop_handler = (
            handler,
            system,
            thread,
            loop_handler,
        )
        return None, None, None

    def uninstall_global_hooks(self, owner: object) -> None:
        """Record cleanup, including partial-install rollback."""
        if owner in self.owners:
            self.owners.remove(owner)
        if not self.owners:
            self.handler = self.system = self.thread = self.loop_handler = None
