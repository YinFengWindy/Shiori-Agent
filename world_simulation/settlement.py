"""Deterministic validation and atomic settlement of world proposals."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from world_simulation.errors import (
    DecisionBarrierBlockedError,
    InvalidWorldProposalError,
    StaleWorldRevisionError,
)
from world_simulation.proposals import BeatProposal
from world_simulation.repository import WorldRepository
from world_simulation.runs import WorldRun
from world_simulation.scenes import DecisionBarrier, SceneThread
from world_simulation.timeline import TimelineEvent, WorldStateProjection


def _merge(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    result = dict(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _merge(result[key], value)
        else:
            result[key] = value
    return result


class WorldSettlement:
    """The sole component allowed to turn proposals into committed world facts."""

    def __init__(self, repository: WorldRepository) -> None:
        self._repository = repository

    def commit(
        self,
        proposal: BeatProposal,
        *,
        request_id: str,
        run: WorldRun | None = None,
        resolved_barrier: DecisionBarrier | None = None,
    ) -> dict[str, Any]:
        """Validate and atomically commit one minimal narrative beat."""

        existing = self._repository.get_idempotency_result(request_id)
        if existing is not None:
            return existing
        proposal.validate_envelope()
        world = self._repository.require_world(proposal.world_id)
        if world.revision != proposal.world_revision:
            raise StaleWorldRevisionError(
                f"stale world revision: expected {proposal.world_revision}, actual {world.revision}"
            )
        if run is not None:
            if run.id != proposal.run_id or run.world_id != world.id:
                raise InvalidWorldProposalError("proposal does not belong to the supplied run")
            if run.random_seed != proposal.random_seed:
                raise InvalidWorldProposalError("proposal random seed differs from its run")

        pending = self._repository.list_pending_barriers(world.id)
        unresolved = [
            item
            for item in pending
            if resolved_barrier is None or item.id != resolved_barrier.id
        ]
        if unresolved:
            boundary = unresolved[0].effective_at
            if any(event.effective_at > boundary for event in proposal.events):
                raise DecisionBarrierBlockedError(
                    f"unresolved barrier prevents advancing beyond {boundary}"
                )

        next_revision = world.revision + 1
        next_sequence = self._repository.next_event_sequence(world.id)
        events = tuple(
            TimelineEvent(
                id=f"event-{uuid4().hex}",
                world_id=world.id,
                event_type=item.event_type,
                effective_at=item.effective_at,
                sequence=next_sequence + index,
                participants=item.participants,
                location=item.location,
                scope=item.scope,
                cause_event_ids=item.cause_event_ids,
                visibility=item.visibility,
                changes=item.changes,
                random_ref=proposal.random_seed,
                is_backfill=item.is_backfill,
                request_id=request_id,
                committed_revision=next_revision,
                dependencies=item.dependencies,
            )
            for index, item in enumerate(proposal.events)
        )
        previous = self._repository.get_projection(world.id)
        cognition = dict(previous.cognition)
        for actor_id, patch in proposal.cognition_patch.items():
            cognition[actor_id] = _merge(cognition.get(actor_id, {}), patch)
        projection = WorldStateProjection(
            world_id=world.id,
            revision=next_revision,
            state=_merge(previous.state, proposal.projection_patch),
            cognition=cognition,
            invalid_after=(
                min(item.effective_at for item in proposal.events if item.is_backfill)
                if any(item.is_backfill for item in proposal.events)
                else previous.invalid_after
            ),
        )
        barrier = self._barrier_from(proposal, world.id)
        scene_thread = self._scene_thread_from(proposal, world.active_oc_id or "")
        committed_run = run
        if committed_run is not None:
            if committed_run.status == "queued":
                committed_run = committed_run.transition("running")
            if committed_run.status == "running":
                committed_run = committed_run.transition("settling")
            committed_run = committed_run.transition(
                "committed", last_committed_revision=next_revision
            )
        result = {
            "world_id": world.id,
            "world_revision": next_revision,
            "event_ids": [item.id for item in events],
            "barrier_id": barrier.id if barrier else None,
            "run_id": proposal.run_id,
        }
        return self._repository.commit_beat(
            world_id=world.id,
            expected_revision=world.revision,
            request_id=request_id,
            events=events,
            projection=projection,
            current_time=max(world.current_time, *(item.effective_at for item in events)),
            result=result,
            run=committed_run,
            barrier=barrier,
            resolved_barrier=resolved_barrier,
            scene_thread=scene_thread,
        )

    @staticmethod
    def _barrier_from(
        proposal: BeatProposal, world_id: str
    ) -> DecisionBarrier | None:
        if proposal.barrier is None:
            return None
        value = proposal.barrier
        required = ("effective_at", "oc_id", "reason")
        if any(not str(value.get(name, "")).strip() for name in required):
            raise InvalidWorldProposalError("decision barrier is missing required fields")
        return DecisionBarrier(
            id=str(value.get("id") or f"barrier-{uuid4().hex}"),
            world_id=world_id,
            effective_at=str(value["effective_at"]),
            oc_id=str(value["oc_id"]),
            reason=str(value["reason"]),
            options=tuple(value.get("options", ())),
        )

    @staticmethod
    def _scene_thread_from(
        proposal: BeatProposal, active_oc_id: str
    ) -> SceneThread | None:
        if proposal.scene_thread is None:
            return None
        value = proposal.scene_thread
        return SceneThread(
            id=str(value.get("id") or f"scene-{uuid4().hex}"),
            world_id=proposal.world_id,
            world_time=str(value.get("world_time") or proposal.events[-1].effective_at),
            location=str(value.get("location") or proposal.events[-1].location),
            participants=dict(value.get("participants", {})),
            active_oc_id=active_oc_id,
            beat_sequence=proposal.beat_sequence,
            status=str(value.get("status", "active")),
            stop_reason=str(value.get("stop_reason", "")),
            barrier_id=(str(value["barrier_id"]) if value.get("barrier_id") else None),
            messages=tuple(value.get("messages", ())),
        )
