"""Small setup surfaces for hook, command, and observation plugins."""

import asyncio
from collections.abc import Coroutine
from typing import Protocol


class ConfigValues(Protocol):
    """Resolved plugin-owned configuration snapshot."""

    def as_dict(self) -> dict[str, object]: ...
    def resolve_reference(self, value: str) -> str:
        """Resolve a stored credential reference at use time without persisting its value."""
        ...


class Dependencies(Protocol):
    """Resolve the current export only for explicitly declared dependencies."""

    def require(self, plugin_id: str) -> object: ...
    def get_optional(self, plugin_id: str) -> object | None: ...


class BackgroundTasks(Protocol):
    """Own cancellable coroutines until plugin cleanup finishes."""

    def spawn[T](
        self, coro: Coroutine[object, object, T], *, name: str
    ) -> asyncio.Task[T]: ...

    def spawn_runtime[T](
        self, coro: Coroutine[object, object, T], *, name: str
    ) -> asyncio.Task[T]:
        """Retain the calling runtime lease until task completion and cleanup."""
        ...
