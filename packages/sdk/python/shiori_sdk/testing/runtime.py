"""Plugin generation draining fixtures."""

from collections.abc import Awaitable, Callable


class FakeRuntimeLifecycle:
    """Record drain requests without constructing a host generation."""

    def __init__(self):
        self.was_active = False
        self.drainers: list[Callable[[], Awaitable[None]]] = []

    def on_drain(self, callback: Callable[[], Awaitable[None]]) -> None:
        """Retain a drainer for an explicit test transition."""
        self.drainers.append(callback)
