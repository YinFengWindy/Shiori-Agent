"""Application facade for persistent world commands."""

from __future__ import annotations

from dataclasses import replace
from typing import Any
from uuid import uuid4

from world_simulation.actors import PlayerOC
from world_simulation.dependencies import DependencySet
from world_simulation.errors import HistoricalConflictError, WorldNotFoundError
from world_simulation.proposals import BeatProposal
from world_simulation.repository import WorldRepository
from world_simulation.runs import WorldRun
from world_simulation.settlement import WorldSettlement
from world_simulation.timeline import TimelineEvent, WorldStateProjection
from world_simulation.world import (
    NativeResident,
    RoleTemplateSnapshot,
    WorldDraft,
    WorldInstance,
    WorldTemplate,
)


class WorldSimulationService:
    """Coordinate world commands while keeping facts behind settlement/repository."""

    def __init__(self, repository: WorldRepository) -> None:
        self.repository = repository
        self.settlement = WorldSettlement(repository)

    def create_draft(
        self,
        *,
        owner_id: str,
        template: WorldTemplate,
        role_snapshots: tuple[RoleTemplateSnapshot, ...],
        residents: tuple[NativeResident, ...],
        initial_time: str,
        creation_metadata: dict[str, Any] | None = None,
        draft_id: str | None = None,
    ) -> WorldDraft:
        """Persist a reviewable draft without creating any world timeline facts."""

        snapshot_ids = {item.id for item in role_snapshots}
        if any(item.snapshot_id not in snapshot_ids for item in residents):
            raise ValueError("every resident must reference a snapshot in the draft")
        draft = WorldDraft(
            id=draft_id or f"draft-{uuid4().hex}",
            owner_id=owner_id,
            template=template,
            role_snapshots=role_snapshots,
            residents=residents,
            initial_time=initial_time,
            creation_metadata=dict(creation_metadata or {}),
        )
        self.repository.save_draft(draft)
        return draft

    def confirm_world(
        self,
        draft_id: str,
        *,
        request_id: str,
        world_id: str | None = None,
        random_seed: str = "initial",
        initial_oc: PlayerOC | None = None,
    ) -> WorldInstance:
        """Atomically confirm a complete draft into the world's initial fact."""

        existing = self.repository.get_idempotency_result(request_id)
        if existing is not None:
            return self.repository.require_world(str(existing["world_id"]))
        draft = self.repository.get_draft(draft_id)
        if draft is None:
            raise WorldNotFoundError(f"world draft not found: {draft_id}")
        if draft.status != "draft":
            raise ValueError(f"world draft is not confirmable: {draft.status}")
        new_world_id = world_id or f"world-{uuid4().hex}"
        world = WorldInstance(
            id=new_world_id,
            owner_id=draft.owner_id,
            template_snapshot=draft.template.to_dict(),
            current_time=draft.initial_time,
            revision=1,
            active_oc_id=initial_oc.id if initial_oc is not None else None,
            random_state=random_seed,
        )
        initial_event = TimelineEvent(
            id=f"event-{uuid4().hex}",
            world_id=new_world_id,
            event_type="world.created",
            effective_at=draft.initial_time,
            sequence=1,
            participants=tuple(
                [*(item.id for item in draft.residents), *([initial_oc.id] if initial_oc else [])]
            ),
            changes={
                "residents": {item.id: item.to_dict() for item in draft.residents},
                "player_ocs": (
                    {initial_oc.id: initial_oc.to_dict()} if initial_oc is not None else {}
                ),
            },
            random_ref=random_seed,
            request_id=request_id,
            committed_revision=1,
            dependencies=DependencySet(
                write_facts=frozenset({"world.created"}),
                write_state=frozenset(
                    f"resident:{item.id}" for item in draft.residents
                ),
            ),
        )
        projection = WorldStateProjection(
            world_id=new_world_id,
            revision=1,
            state={
                "residents": {item.id: item.to_dict() for item in draft.residents},
                "player_ocs": (
                    {initial_oc.id: initial_oc.to_dict()} if initial_oc is not None else {}
                ),
            },
            cognition={initial_oc.id: dict(initial_oc.cognition)} if initial_oc else {},
        )
        result = {"world_id": new_world_id, "world_revision": 1}
        self.repository.create_world_from_draft(
            draft,
            world,
            initial_event,
            projection,
            request_id=request_id,
            result=result,
            initial_oc=initial_oc,
        )
        return self.repository.require_world(new_world_id)

    def add_oc(
        self,
        world_id: str,
        oc: PlayerOC,
        *,
        entry_time: str,
        expected_revision: int,
        request_id: str,
        dependencies: DependencySet | None = None,
    ) -> dict[str, Any]:
        """Add an OC now or by safe append-only historical backfill."""

        existing = self.repository.get_idempotency_result(request_id)
        if existing is not None:
            return existing
        world = self.repository.require_world(world_id)
        backfill = entry_time < world.current_time
        dependency_set = dependencies or DependencySet(
            write_facts=frozenset({f"oc:{oc.id}:exists"}),
            write_state=frozenset({f"oc:{oc.id}"}),
            write_cognition=frozenset({f"oc:{oc.id}:private_history"}),
        )
        if backfill:
            self._validate_backfill(world_id, entry_time, dependency_set)
        revision = expected_revision + 1
        event = TimelineEvent(
            id=f"event-{uuid4().hex}",
            world_id=world_id,
            event_type="player_oc.backfilled" if backfill else "player_oc.joined",
            effective_at=entry_time,
            sequence=self.repository.next_event_sequence(world_id),
            participants=(oc.id,),
            changes={"player_ocs": {oc.id: oc.to_dict()}},
            is_backfill=backfill,
            request_id=request_id,
            committed_revision=revision,
            dependencies=dependency_set,
        )
        previous = self.repository.get_projection(world_id)
        state = dict(previous.state)
        state["player_ocs"] = {
            **dict(state.get("player_ocs", {})),
            oc.id: oc.to_dict(),
        }
        cognition = dict(previous.cognition)
        cognition[oc.id] = dict(oc.cognition)
        projection = WorldStateProjection(
            world_id=world_id,
            revision=revision,
            state=state,
            cognition=cognition,
            invalid_after=entry_time if backfill else previous.invalid_after,
        )
        result = {
            "world_id": world_id,
            "world_revision": revision,
            "oc_id": oc.id,
            "event_id": event.id,
            "is_backfill": backfill,
        }
        return self.repository.add_oc(
            world_id,
            oc,
            entry_time,
            expected_revision=expected_revision,
            request_id=request_id,
            event=event,
            projection=projection,
            result=result,
        )

    def switch_oc(
        self, world_id: str, oc_id: str, *, expected_revision: int
    ) -> WorldInstance:
        """Switch the directly controlled OC without advancing the shared clock."""

        return self.repository.update_active_oc(world_id, oc_id, expected_revision)

    def start_run(
        self,
        world_id: str,
        *,
        kind: str,
        request_id: str,
        expected_revision: int,
        random_seed: str,
    ) -> WorldRun:
        """Persist a queued run and return its stable id before any generation."""

        previous = self.repository.get_run_by_request(request_id)
        if previous is not None:
            return previous
        world = self.repository.require_world(world_id)
        if world.revision != expected_revision:
            from world_simulation.errors import StaleWorldRevisionError

            raise StaleWorldRevisionError(
                f"stale world revision: expected {expected_revision}, actual {world.revision}"
            )
        run = WorldRun(
            id=f"run-{uuid4().hex}",
            request_id=request_id,
            world_id=world_id,
            kind=kind,
            starting_revision=expected_revision,
            random_seed=random_seed,
        )
        self.repository.save_run(run)
        return run

    def submit_action(
        self, proposal: BeatProposal, *, request_id: str
    ) -> dict[str, Any]:
        """Settle one action beat using the proposal's persisted run."""

        run = self.repository.get_run(proposal.run_id)
        if run is None:
            raise WorldNotFoundError(f"world run not found: {proposal.run_id}")
        return self.settlement.commit(proposal, request_id=request_id, run=run)

    def advance(self, proposal: BeatProposal, *, request_id: str) -> dict[str, Any]:
        """Settle one whole-world progression beat."""

        return self.submit_action(proposal, request_id=request_id)

    def resolve_barrier(
        self,
        world_id: str,
        barrier_id: str,
        proposal: BeatProposal,
        *,
        request_id: str,
        resolution: dict[str, Any],
    ) -> dict[str, Any]:
        """Commit a player's decision and resolve exactly one queued barrier."""

        barrier = self.repository.get_barrier(world_id, barrier_id)
        if barrier is None or barrier.status != "pending":
            raise WorldNotFoundError(f"pending barrier not found: {barrier_id}")
        resolved = replace(barrier, status="resolved", resolution=resolution)
        run = self.repository.get_run(proposal.run_id)
        if run is None:
            raise WorldNotFoundError(f"world run not found: {proposal.run_id}")
        return self.settlement.commit(
            proposal,
            request_id=request_id,
            run=run,
            resolved_barrier=resolved,
        )

    def copy_world(
        self,
        source_world_id: str,
        event_id: str,
        *,
        request_id: str,
        new_world_id: str | None = None,
    ) -> WorldInstance:
        """Copy a committed timeline prefix into an independently evolving world."""

        existing = self.repository.get_idempotency_result(request_id)
        if existing is not None:
            return self.repository.require_world(str(existing["world_id"]))
        source = self.repository.require_world(source_world_id)
        event = self.repository.get_event(source_world_id, event_id)
        if event is None:
            raise WorldNotFoundError(f"timeline event not found: {event_id}")
        source_projection = self.repository.get_projection_at_revision(
            source_world_id, event.committed_revision
        )
        if source_projection is None:
            raise WorldNotFoundError(
                f"world cannot be restored at revision {event.committed_revision}"
            )
        target_id = new_world_id or f"world-{uuid4().hex}"
        target = WorldInstance(
            id=target_id,
            owner_id=source.owner_id,
            template_snapshot=source.template_snapshot,
            current_time=event.effective_at,
            revision=event.committed_revision,
            active_oc_id=source.active_oc_id,
            parent_world_id=source_world_id,
            fork_event_id=event_id,
            random_state=f"fork:{source.random_state}:{event_id}:{target_id}",
        )
        projection = replace(source_projection, world_id=target_id)
        result = {
            "world_id": target_id,
            "parent_world_id": source_world_id,
            "fork_event_id": event_id,
            "world_revision": event.committed_revision,
        }
        self.repository.copy_world_prefix(
            source_world_id=source_world_id,
            through_event=event,
            target=target,
            projection=projection,
            request_id=request_id,
            result=result,
        )
        return self.repository.require_world(target_id)

    def cancel_run(self, run_id: str) -> WorldRun:
        """Prevent a run from starting another beat while preserving committed facts."""

        run = self.repository.get_run(run_id)
        if run is None:
            raise WorldNotFoundError(f"world run not found: {run_id}")
        if run.status == "cancelled":
            return run
        cancelled = run.transition("cancelled")
        self.repository.save_run(cancelled)
        return cancelled

    def _validate_backfill(
        self, world_id: str, effective_at: str, backfill: DependencySet
    ) -> None:
        conflicts: set[str] = set()
        for event in self.repository.list_events_after_effective_at(
            world_id, effective_at
        ):
            conflicts.update(backfill.conflicts_with(event.dependencies))
        if conflicts:
            raise HistoricalConflictError(
                "historical backfill conflicts with settled causal dependencies: "
                + ", ".join(sorted(conflicts))
            )
