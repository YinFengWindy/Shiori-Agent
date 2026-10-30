"""Generation-owned subscription supplying neutral scene facts to followup state."""

from bus.event_bus import EventBus
from core.roles.affection_access import AffectionGetter
from shiori_sdk.role_events import SceneObservationCommitted


class SceneFollowupSubscription:
    """Subscribes only on publication and releases the exact registered callback."""

    def __init__(self, bus: EventBus, affection: AffectionGetter) -> None:
        self._bus = bus
        self._affection = affection
        self._handler = self._apply
        self._started = False

    def start(self) -> None:
        """Activates once after this generation has been published."""
        if not self._started:
            self._bus.on(SceneObservationCommitted, self._handler)
            self._started = True

    def stop(self) -> None:
        """Detaches on rollback or after accepted generation work has drained."""
        if self._started:
            self._bus.off(SceneObservationCommitted, self._handler)
            self._started = False

    def _apply(self, event: SceneObservationCommitted) -> None:
        runtime = self._affection() if self._affection.bound else None
        if runtime is None:
            return
        runtime.apply_scene_decision(
            event.session_key, event.transition, event.scene_key
        )
