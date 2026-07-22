"""Official relationship-driven admission policies for proactive turns."""

from __future__ import annotations

from agent.core.proactive_turn.gates import (
    ProactiveGateAdapter,
    ProactiveGateCompletion,
    ProactiveGateContext,
    ProactiveGateDecision,
    ProactiveMode,
)
from agent.plugins import Plugin
from bus.events_lifecycle import SceneObservationCommitted
from core.roles.relationship_runtime import RoleRelationshipRuntimeService


class _SceneFollowupGate(ProactiveGateAdapter):
    name = "relationship.scene_followup"
    priority = 100

    def __init__(self, runtime: RoleRelationshipRuntimeService) -> None:
        self._runtime = runtime

    def evaluate(self, ctx: ProactiveGateContext) -> ProactiveGateDecision:
        should_follow_up, metadata = self._runtime.should_trigger_scene_followup(
            ctx.session_key,
            ctx.now_utc,
        )
        if not should_follow_up:
            return ProactiveGateDecision.continue_()
        return ProactiveGateDecision.activate(
            ProactiveMode.SCENE_FOLLOWUP,
            reason="scene_followup",
            metadata=metadata,
        )

    def finalize(self, completion: ProactiveGateCompletion) -> None:
        if completion.outcome == "delivered":
            self._runtime.handle_scene_followup_sent(
                completion.session_key,
                completion.occurred_at,
            )
            return
        self._runtime.close_scene_followup(completion.session_key)


class _LonelinessGate(ProactiveGateAdapter):
    name = "relationship.loneliness"
    priority = 0

    def __init__(self, runtime: RoleRelationshipRuntimeService) -> None:
        self._runtime = runtime

    def evaluate(self, ctx: ProactiveGateContext) -> ProactiveGateDecision:
        should_trigger, metadata = self._runtime.should_trigger_proactive(
            ctx.session_key,
            ctx.now_utc,
        )
        if not should_trigger:
            return ProactiveGateDecision.block("loneliness")
        return ProactiveGateDecision.activate(
            ProactiveMode.RELATIONSHIP_FALLBACK,
            reason="loneliness",
            metadata=metadata,
        )


class RelationshipProactivePlugin(Plugin):
    """Adapts the relationship runtime to the proactive gate seam."""

    name = "relationship_proactive"

    async def initialize(self) -> None:
        self._scene_handler = self._handle_scene_observation
        self.context.event_bus.on(SceneObservationCommitted, self._scene_handler)

    def _handle_scene_observation(self, event: SceneObservationCommitted) -> None:
        runtime = self.context.relationship_runtime
        if runtime is None:
            return
        runtime.apply_scene_decision(
            event.session_key,
            event.transition,
            event.scene_key,
        )

    def proactive_gates(self):
        runtime = self.context.relationship_runtime
        if runtime is None:
            return []
        return [_SceneFollowupGate(runtime), _LonelinessGate(runtime)]

    async def terminate(self) -> None:
        handler = getattr(self, "_scene_handler", None)
        if handler is not None:
            self.context.event_bus.off(SceneObservationCommitted, handler)
