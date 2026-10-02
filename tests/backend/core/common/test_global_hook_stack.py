"""Multi-generation ownership of process-wide exception hooks.

Owners are neutral recorders: the stack must route logs and hooks to the
newest live owner regardless of which plugin generation retires first.
"""

import asyncio
import logging
import sys
import threading

from core.common.global_hook_stack import install_global_hooks, uninstall_global_hooks


class _Owner(logging.Handler):
    """One hook generation that records the log records it receives."""

    def __init__(self) -> None:
        super().__init__(logging.ERROR)
        self.records: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record.getMessage())

    def system(self, *_args) -> None:
        """Process exception hook owned by this generation."""

    def thread(self, _args) -> None:
        """Thread exception hook owned by this generation."""

    def loop_handler(self, _loop, _context) -> None:
        """Event-loop exception handler owned by this generation."""

    def install(self) -> None:
        install_global_hooks(
            self,
            self,
            self.system,
            self.thread,
            asyncio.get_running_loop(),
            self.loop_handler,
        )


def _assert_active(owner: _Owner) -> None:
    assert sys.excepthook == owner.system
    assert threading.excepthook == owner.thread
    assert asyncio.get_running_loop().get_exception_handler() == owner.loop_handler


async def test_retiring_the_old_owner_keeps_the_new_owner_and_records_once():
    previous = (
        sys.excepthook,
        threading.excepthook,
        asyncio.get_running_loop().get_exception_handler(),
    )
    old, new = _Owner(), _Owner()
    old.install()
    new.install()
    try:
        logging.getLogger("app.test").error("one observed error")
        uninstall_global_hooks(old)
        _assert_active(new)
        uninstall_global_hooks(new)
        assert old.records == []
        assert new.records == ["one observed error"]
        assert (
            sys.excepthook,
            threading.excepthook,
            asyncio.get_running_loop().get_exception_handler(),
        ) == previous
    finally:
        uninstall_global_hooks(new)
        uninstall_global_hooks(old)


async def test_discarding_the_newest_owner_restores_the_active_generation():
    active, candidate = _Owner(), _Owner()
    active.install()
    candidate.install()
    try:
        uninstall_global_hooks(candidate)
        _assert_active(active)
        logging.getLogger("app.test").error("active remains")
        uninstall_global_hooks(active)
        assert active.records == ["active remains"]
        assert candidate.records == []
    finally:
        uninstall_global_hooks(candidate)
        uninstall_global_hooks(active)
