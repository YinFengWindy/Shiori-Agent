import pytest

from world_simulation.errors import DecisionBarrierBlockedError
from world_simulation.proposals import BeatProposal, ProposedEvent
from world_simulation.repository import WorldRepository
from world_simulation.service import WorldSimulationService


def proposal(world_id, revision, run_id, seed, *, at, barrier=None, name="beat"):
    return BeatProposal(
        schema_version=1,
        proposal_id=f"proposal-{name}",
        proposal_type="scene_beat",
        world_id=world_id,
        world_revision=revision,
        run_id=run_id,
        beat_sequence=1,
        provider="test",
        model="deterministic",
        prompt_version="v1",
        random_seed=seed,
        source="test",
        events=(
            ProposedEvent(
                event_type=name,
                effective_at=at,
                changes={"last": name},
            ),
        ),
        projection_patch={"last": name},
        barrier=barrier,
    )


def test_settlement_is_idempotent_and_commits_run_with_outbox(
    service: WorldSimulationService, repository: WorldRepository, world
):
    run = service.start_run(
        world.id,
        kind="action",
        request_id="run-request",
        expected_revision=1,
        random_seed="seed-1",
    )
    beat = proposal(
        world.id,
        1,
        run.id,
        "seed-1",
        at="2026-04-01T09:00:00+00:00",
    )

    first = service.submit_action(beat, request_id="beat-request")
    second = service.submit_action(beat, request_id="beat-request")

    assert second == first
    assert repository.require_world(world.id).revision == 2
    assert len(repository.list_events(world.id)) == 2
    assert repository.get_run(run.id).status == "committed"
    assert len(repository.list_outbox(world.id)) == 2


def test_unresolved_barrier_blocks_later_world_time(
    service: WorldSimulationService, repository: WorldRepository, world
):
    run = service.start_run(
        world.id,
        kind="advance",
        request_id="run-barrier",
        expected_revision=1,
        random_seed="seed-b",
    )
    beat = proposal(
        world.id,
        1,
        run.id,
        "seed-b",
        at="2026-04-01T10:00:00+00:00",
        barrier={
            "id": "barrier-1",
            "effective_at": "2026-04-01T10:00:00+00:00",
            "oc_id": "oc-1",
            "reason": "major choice",
        },
        name="choice.arrived",
    )
    service.advance(beat, request_id="beat-barrier")
    next_run = service.start_run(
        world.id,
        kind="advance",
        request_id="run-blocked",
        expected_revision=2,
        random_seed="seed-c",
    )
    later = proposal(
        world.id,
        2,
        next_run.id,
        "seed-c",
        at="2026-04-01T11:00:00+00:00",
        name="too.late",
    )

    with pytest.raises(DecisionBarrierBlockedError):
        service.advance(later, request_id="beat-blocked")

    assert repository.require_world(world.id).revision == 2
    assert len(repository.list_events(world.id)) == 2


def test_resolving_barrier_commits_decision_and_clears_queue(
    service: WorldSimulationService, repository: WorldRepository, world
):
    first_run = service.start_run(
        world.id,
        kind="advance",
        request_id="run-create-choice",
        expected_revision=1,
        random_seed="seed-choice",
    )
    service.advance(
        proposal(
            world.id,
            1,
            first_run.id,
            "seed-choice",
            at="2026-04-01T10:00:00+00:00",
            barrier={
                "id": "barrier-resolve",
                "effective_at": "2026-04-01T10:00:00+00:00",
                "oc_id": "oc-1",
                "reason": "choose a direction",
            },
            name="choice.required",
        ),
        request_id="beat-create-choice",
    )
    resolve_run = service.start_run(
        world.id,
        kind="resolve_barrier",
        request_id="run-resolve-choice",
        expected_revision=2,
        random_seed="seed-resolution",
    )
    decision = proposal(
        world.id,
        2,
        resolve_run.id,
        "seed-resolution",
        at="2026-04-01T10:00:00+00:00",
        name="choice.resolved",
    )

    service.resolve_barrier(
        world.id,
        "barrier-resolve",
        decision,
        request_id="beat-resolve-choice",
        resolution={"option": "stay"},
    )

    assert repository.list_pending_barriers(world.id) == []
    assert repository.require_world(world.id).revision == 3
