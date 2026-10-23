"""Publication-scoped ownership of scene intake and background tasks."""

from bus.event_bus import EventBus
from shiori_sdk.core.conversation import TurnFinished, TurnStarting
from bus.events_lifecycle import ProactiveMessageCommitted
from core.scene.controller import SceneAwarenessController


class SceneObservationService:
    """Keeps prepared generations inert until the runtime publishes them."""

    def __init__(
        self, controller: SceneAwarenessController, event_bus: EventBus
    ) -> None:
        self.controller = controller
        self._bus = event_bus
        self._active = False
        self._capture = controller.capture_passive_turn
        self._passive = controller.schedule_passive_turn
        self._proactive = controller.schedule_proactive_turn

    def activate(self) -> None:
        """Starts intake only after publication; repeated activation is harmless."""
        if self._active:
            return
        self._active = True
        self._bus.on(TurnStarting, self._capture)
        self._bus.on(TurnFinished, self._passive)
        self._bus.on(ProactiveMessageCommitted, self._proactive)

    def deactivate(self) -> None:
        """Closes intake before any task cancellation or asynchronous cleanup."""
        if not self._active:
            return
        self._active = False
        self._bus.off(TurnStarting, self._capture)
        self._bus.off(TurnFinished, self._passive)
        self._bus.off(ProactiveMessageCommitted, self._proactive)

    async def close(self) -> None:
        """Stops intake, cancels observations, and waits for all displaced tasks."""
        self.deactivate()
        await self.controller.terminate()
