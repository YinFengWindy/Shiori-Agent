from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import Any, TypeVar

from bus.event_bus import EventBus, Handler

T = TypeVar("T")


class PluginEventBus:
    """Delegates EventBus operations while tracking plugin-owned subscriptions."""

    def __init__(self, event_bus: EventBus) -> None:
        self._event_bus = event_bus
        self._bindings: list[tuple[type[object], Handler[object]]] = []

    def on(self, event_type: type[T], handler: Handler[T]) -> None:
        self._event_bus.on(event_type, handler)
        self._bindings.append((event_type, handler))  # type: ignore[list-item]

    def off(self, event_type: type[T], handler: Handler[T]) -> None:
        self._event_bus.off(event_type, handler)
        target = (event_type, handler)
        self._bindings = [binding for binding in self._bindings if binding != target]

    def __getattr__(self, name: str) -> Any:
        return getattr(self._event_bus, name)

    def release(self) -> None:
        for event_type, handler in reversed(self._bindings):
            self._event_bus.off(event_type, handler)
        self._bindings.clear()


class PluginToolRegistry:
    """Delegates ToolRegistry operations while tracking plugin-owned tools."""

    def __init__(self, registry: Any) -> None:
        self._registry = registry
        self._tool_names: set[str] = set()

    def register(self, tool: Any, **kwargs: Any) -> None:
        self._registry.register(tool, **kwargs)
        self._tool_names.add(str(tool.name))

    def unregister(self, name: str) -> None:
        self._registry.unregister(name)
        self._tool_names.discard(name)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._registry, name)

    def release(self) -> None:
        for name in tuple(self._tool_names):
            self._registry.unregister(name)
        self._tool_names.clear()


class PluginResourceScope:
    """Owns resources registered by one plugin for deterministic cleanup."""

    def __init__(self, event_bus: EventBus, tool_registry: Any) -> None:
        self.event_bus = PluginEventBus(event_bus)
        self.tool_registry = (
            PluginToolRegistry(tool_registry) if tool_registry is not None else None
        )
        self._tasks: set[asyncio.Task[Any]] = set()

    def create_task(
        self,
        coroutine: Coroutine[Any, Any, T],
        *,
        name: str | None = None,
    ) -> asyncio.Task[T]:
        """Creates a plugin-owned task cancelled and awaited during unload."""

        task = asyncio.create_task(coroutine, name=name)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task

    async def release(self) -> None:
        self.event_bus.release()
        if self.tool_registry is not None:
            self.tool_registry.release()
        tasks = tuple(self._tasks)
        self._tasks.clear()
        for task in tasks:
            if not task.done():
                task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
