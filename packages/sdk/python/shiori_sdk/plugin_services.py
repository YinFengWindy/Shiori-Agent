"""Lifecycle of work a plugin accepted for one kernel generation."""

from collections.abc import Awaitable, Callable
from typing import Protocol


class RuntimeLifecycle(Protocol):
    """Retain accepted work until a replacing generation has drained it."""

    @property
    def was_active(self) -> bool: ...
    def on_drain(self, callback: Callable[[], Awaitable[None]]) -> None:
        """Only wait for accepted work (no teardown); may run more than once,
        including while the instance stays active after an abandoned reload."""
        ...
