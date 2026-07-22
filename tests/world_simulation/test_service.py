import pytest

from world_simulation.actors import PlayerOC
from world_simulation.dependencies import DependencySet
from world_simulation.errors import HistoricalConflictError
from world_simulation.proposals import BeatProposal, ProposedEvent
from world_simulation.repository import WorldRepository
from world_simulation.service import WorldSimulationService


def make_oc(oc_id: str) -> PlayerOC:
    return PlayerOC(
        id=oc_id,
        name=oc_id,
        persona={"trait": "curious"},
        identity={"occupation": "student"},
        primary_goal="graduate",
        location="library",
    )


def test_multiple_ocs_share_clock_and_switching_does_not_advance_it(
    service: WorldSimulationService, repository: WorldRepository, world
):
    first = service.add_oc(
        world.id,
        make_oc("oc-a"),
        entry_time=world.current_time,
        expected_revision=1,
        request_id="add-a",
    )
    second = service.add_oc(
        world.id,
        make_oc("oc-b"),
        entry_time=world.current_time,
        expected_revision=first["world_revision"],
        request_id="add-b",
    )
    before = repository.require_world(world.id)

    switched = service.switch_oc(
        world.id, "oc-b", expected_revision=second["world_revision"]
    )

    assert len(repository.list_ocs(world.id)) == 2
    assert switched.active_oc_id == "oc-b"
    assert switched.current_time == before.current_time
    assert switched.revision == before.revision


def test_confirming_a_world_persists_its_first_oc_in_the_same_initial_fact(
    service: WorldSimulationService, repository: WorldRepository
):
    from world_simulation.world import NativeResident, RoleTemplateSnapshot, WorldTemplate

    snapshot = RoleTemplateSnapshot(
        id="snapshot-first-oc",
        source_role_id="rin",
        source_version="v1",
        persona={"temperament": "calm"},
    )
    draft = service.create_draft(
        owner_id="player-1",
        template=WorldTemplate(id="template", name="World", era="modern"),
        role_snapshots=(snapshot,),
        residents=(NativeResident(id="resident", snapshot_id=snapshot.id, name="Rin"),),
        initial_time="2026-04-01T08:00:00+00:00",
    )

    created = service.confirm_world(
        draft.id,
        request_id="confirm-with-first-oc",
        initial_oc=make_oc("oc-first"),
    )

    assert created.active_oc_id == "oc-first"
    assert [item.id for item in repository.list_ocs(created.id)] == ["oc-first"]
    initial_event = repository.list_events(created.id)[0]
    assert initial_event.participants == ("resident", "oc-first")


def test_historical_backfill_rejects_dependency_conflict_without_partial_writes(
    service: WorldSimulationService, repository: WorldRepository, world
):
    run = service.start_run(
        world.id,
        kind="action",
        request_id="causal-run",
        expected_revision=1,
        random_seed="causal-seed",
    )
    proposal = BeatProposal(
        schema_version=1,
        proposal_id="causal-proposal",
        proposal_type="scene_beat",
        world_id=world.id,
        world_revision=1,
        run_id=run.id,
        beat_sequence=1,
        provider="test",
        model="test",
        prompt_version="v1",
        random_seed="causal-seed",
        source="test",
        events=(
            ProposedEvent(
                event_type="meeting.decided",
                effective_at="2026-04-02T09:00:00+00:00",
                dependencies=DependencySet(
                    read_facts=frozenset({"relationship:new:rin"})
                ),
            ),
        ),
    )
    service.submit_action(proposal, request_id="causal-beat")
    revision = repository.require_world(world.id).revision
    count = len(repository.list_events(world.id))

    with pytest.raises(HistoricalConflictError):
        service.add_oc(
            world.id,
            make_oc("oc-new"),
            entry_time="2026-04-01T12:00:00+00:00",
            expected_revision=revision,
            request_id="conflicting-backfill",
            dependencies=DependencySet(
                write_facts=frozenset({"relationship:new:rin"})
            ),
        )

    assert repository.require_world(world.id).revision == revision
    assert len(repository.list_events(world.id)) == count
    assert repository.list_ocs(world.id) == []


def test_copy_uses_committed_node_and_evolves_independently(
    service: WorldSimulationService, repository: WorldRepository, world
):
    joined = service.add_oc(
        world.id,
        make_oc("oc-a"),
        entry_time=world.current_time,
        expected_revision=1,
        request_id="copy-add-a",
    )
    copy = service.copy_world(
        world.id,
        joined["event_id"],
        request_id="copy-request",
        new_world_id="world-copy",
    )

    service.add_oc(
        copy.id,
        make_oc("oc-copy-only"),
        entry_time=copy.current_time,
        expected_revision=copy.revision,
        request_id="copy-add-only",
    )

    assert copy.parent_world_id == world.id
    assert {item.id for item in repository.list_ocs(world.id)} == {"oc-a"}
    assert {item.id for item in repository.list_ocs(copy.id)} == {
        "oc-a",
        "oc-copy-only",
    }
    assert repository.require_world(world.id).revision == 2
    assert repository.require_world(copy.id).revision == 3


def test_cancel_queued_run_is_persistent_and_idempotent(
    service: WorldSimulationService, repository: WorldRepository, world
):
    run = service.start_run(
        world.id,
        kind="advance",
        request_id="cancel-run",
        expected_revision=1,
        random_seed="cancel-seed",
    )

    cancelled = service.cancel_run(run.id)
    repeated = service.cancel_run(run.id)

    assert cancelled.status == repeated.status == "cancelled"
    assert repository.get_run(run.id).status == "cancelled"
