"""Generation-owned subscription supplying neutral scene facts to followup state."""

from bus.event_bus import EventBus
from shiori_sdk.role_events import SceneObservationCommitted
from core.roles.relationship_runtime import RoleRelationshipRuntimeService


class SceneFollowupSubscription:
    """Subscribes only on publication and releases the exact registered callback."""

    def __init__(self, bus: EventBus, runtime: RoleRelationshipRuntimeService) -> None:
        self._bus = bus
        self._runtime = runtime
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
        self._runtime.apply_scene_decision(
            event.session_key, event.transition, event.scene_key
        )
