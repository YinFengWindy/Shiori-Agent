"""The scene plugin's demand registry and publication-scoped intake."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Coroutine
from typing import Any

from shiori_sdk.core.conversation import (
    InitiatedMessageCommitted,
    TurnFinished,
    TurnStarting,
)
from shiori_sdk.core.scene import SceneHost
from shiori_sdk.roles import RoleView, Roles
from shiori_sdk.role_events import SceneObservationCommitted
from shiori_sdk.runtime import EventsCapability

from .controller import SceneAwarenessController
from .state import SceneStateStore

type _Spawn = Callable[[Coroutine[Any, Any, None], str], Any]
type _Publish = Callable[[SceneObservationCommitted], Awaitable[None]]


class SceneObservationDemand:
    """Consumer predicates. Registration returns its disposer."""

    def __init__(self) -> None:
        self._consumers: dict[object, Callable[[RoleView], bool]] = {}

    def register(self, predicate: Callable[[RoleView], bool]) -> Callable[[], None]:
        """Registers demand without starting observation."""
        key = object()
        self._consumers[key] = predicate

        def dispose() -> None:
            self._consumers.pop(key, None)

        return dispose

    def needed(self, role: RoleView) -> bool:
        """Whether any installed consumer requests this role's observations."""
        return any(predicate(role) for predicate in self._consumers.values())


class SceneService:
    """Demand, intake and background tasks of one generation's scene plugin."""

    def __init__(
        self,
        *,
        host: SceneHost,
        roles: Roles,
        state: SceneStateStore,
        light_provider: object,
        light_model: str,
        spawn: _Spawn,
        publish: _Publish,
        events: EventsCapability,
        observation_enabled: bool,
    ) -> None:
        self._demand = SceneObservationDemand()
        self._roles = roles
        self._events = events
        self._active = False
        self._controller = SceneAwarenessController(
            host=host,
            state=state,
            light_provider=light_provider,
            light_model=light_model,
            spawn=spawn,
            publish=publish,
            needs_observation=lambda role_id: observation_enabled
            and self._role_needed(role_id, host),
        )
        self._capture = self._on_turn_starting
        self._passive = self._on_turn_finished
        self._proactive = self._controller.schedule_proactive_turn

    def request(self, predicate: Callable[[RoleView], bool]) -> Callable[[], None]:
        """Register demand. The caller effects the disposer."""
        return self._demand.register(predicate)

    def activate(self) -> None:
        """Starts intake. Runs through ``SceneHost.on_published``."""
        if self._active:
            return
        self._active = True
        self._events.on(TurnStarting, self._capture)
        self._events.on(TurnFinished, self._passive)
        self._events.on(InitiatedMessageCommitted, self._proactive)

    def deactivate(self) -> None:
        """Closes intake before task cancellation."""
        if not self._active:
            return
        self._active = False
        self._events.off(TurnStarting, self._capture)
        self._events.off(TurnFinished, self._passive)
        self._events.off(InitiatedMessageCommitted, self._proactive)

    async def close(self) -> None:
        """Stops intake and waits for displaced observations."""
        self.deactivate()
        await self._controller.terminate()

    async def _on_turn_starting(self, event: TurnStarting) -> TurnStarting:
        self._controller.capture_passive_turn(event)
        return event

    async def _on_turn_finished(self, event: TurnFinished) -> TurnFinished:
        self._controller.schedule_passive_turn(event)
        return event

    def _role_needed(self, role_id: str, host: SceneHost) -> bool:
        role = self._roles.get_role(role_id)
        demanded = role is not None and self._demand.needed(role)
        return demanded or host.followup_wanted(role_id)
