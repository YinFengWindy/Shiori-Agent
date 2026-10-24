from __future__ import annotations

from collections.abc import Awaitable, Callable

from bus.event_bus import EventBus
from shiori_sdk.core.conversation import StepFinished


class TurnLifecycle:
    """Core listeners of the turn events the turn stages fan out on the core bus."""

    def __init__(self, bus: EventBus) -> None:
        self._bus = bus

    def on_step_finished(
        self,
        handler: Callable[[StepFinished], Awaitable[None] | None],
    ) -> None:
        """Listens to the final ``StepFinished`` the turn fans out to the core bus."""
        self._bus.on(StepFinished, handler)
