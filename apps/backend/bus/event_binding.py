"""Typed event/callback pairs with stable identity across channel restarts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, TypeVar

from shiori_sdk.runtime import EventsCapability as EventBus, EventHandler as Handler

E = TypeVar("E")


@dataclass(frozen=True)
class EventBinding(Generic[E]):
    """Keeps an event type coupled to its handler when storing mixed bindings."""

    event_type: type[E]
    handler: Handler[E]

    def bind(self, bus: EventBus) -> None:
        """Registers the captured handler with its matching event type."""
        bus.on(self.event_type, self.handler)

    def unbind(self, bus: EventBus) -> None:
        """Removes the same handler object that was originally registered."""
        bus.off(self.event_type, self.handler)
