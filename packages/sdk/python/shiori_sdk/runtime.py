"""Granted runtime interfaces; the SDK never creates host services or storage."""

from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Protocol

from .lifecycle import LifecycleCapability

type Dispose = Callable[[], Awaitable[None] | None]
type EventHandler[EventT] = Callable[[EventT], Awaitable[EventT | None] | EventT | None]


class CapabilityNotGranted(AttributeError):
    """The plugin tried to access a capability absent from its manifest."""


class EventsCapability(Protocol):
    """Scoped typed subscriptions and sequential event dispatch."""

    def on[EventT](
        self, event_type: type[EventT], handler: EventHandler[EventT]
    ) -> None: ...

    def off[EventT](
        self, event_type: type[EventT], handler: EventHandler[EventT]
    ) -> None: ...

    async def emit[EventT](self, event: EventT) -> EventT: ...


class PluginRuntimeContext(Protocol):
    """Public setup context. Undeclared capabilities raise CapabilityNotGranted."""

    @property
    def plugin_id(self) -> str: ...

    @property
    def plugin_dir(self) -> Path: ...

    @property
    def granted(self) -> tuple[str, ...]: ...

    @property
    def lifecycle(self) -> LifecycleCapability: ...

    @property
    def events(self) -> EventsCapability: ...

    def expose(self, api: object) -> None: ...

    def effect(self, label: str, dispose: Dispose) -> None: ...
