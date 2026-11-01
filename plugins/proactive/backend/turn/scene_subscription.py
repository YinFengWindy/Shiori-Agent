"""One generation's subscription of scene facts into its affection runtime."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol

from shiori_sdk.core.affection import Affection
from shiori_sdk.role_events import SceneObservationCommitted


class _EventBus(Protocol):
    def on(self, event_type: type, handler: Callable[..., Any]) -> None: ...

    def off(self, event_type: type, handler: Callable[..., Any]) -> None: ...


class SceneFollowupSubscription:
    """Subscribes on publication and releases that exact callback."""

    def __init__(
        self, bus: _EventBus, affection: Callable[[], Affection | None]
    ) -> None:
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
        """Detaches when this generation is unloaded."""
        if self._started:
            self._bus.off(SceneObservationCommitted, self._handler)
            self._started = False

    def _apply(self, event: SceneObservationCommitted) -> None:
        runtime = self._affection()
        if runtime is None:
            return
        runtime.apply_scene_decision(
            event.session_key, event.transition, event.scene_key
        )
