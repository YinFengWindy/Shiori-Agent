from world_simulation.repository import WorldRepository
from world_simulation.presentation_session import WorldPresentationSession


def test_confirmed_world_persists_fact_projection_idempotency_and_outbox(
    repository: WorldRepository, world
):
    assert repository.require_world(world.id).revision == 1
    assert [event.event_type for event in repository.list_events(world.id)] == [
        "world.created"
    ]
    assert repository.get_projection(world.id).revision == 1
    assert repository.get_idempotency_result("confirm-1") == {
        "world_id": world.id,
        "world_revision": 1,
    }
    notices = repository.list_outbox(world.id)
    assert len(notices) == 1
    assert notices[0]["event_type"] == "SceneBeatCommitted"


def test_outbox_cursor_replays_without_duplicates(repository: WorldRepository, world):
    notice = repository.list_outbox(world.id)[0]
    repository.acknowledge_outbox("desktop", world.id, notice["sequence"])
    repository.acknowledge_outbox("desktop", world.id, 0)

    assert repository.consumer_cursor("desktop", world.id) == notice["sequence"]
    assert repository.list_outbox(
        world.id, after_sequence=repository.consumer_cursor("desktop", world.id)
    ) == []


def test_presentation_session_survives_restart_and_can_be_rebuilt(
    repository: WorldRepository, world, tmp_path
):
    repository.save_presentation_session(
        WorldPresentationSession(
            world_id=world.id,
            last_presented_event_sequence=1,
            active_plan_id="plan-1",
            active_cue_index=2,
            status="paused",
            updated_at="2026-04-01T09:00:00+00:00",
        )
    )
    repository.close()

    restarted = WorldRepository(tmp_path / "worlds.db")
    assert restarted.get_presentation_session(world.id) == WorldPresentationSession(
        world_id=world.id,
        last_presented_event_sequence=1,
        active_plan_id="plan-1",
        active_cue_index=2,
        status="paused",
        updated_at="2026-04-01T09:00:00+00:00",
    )
    restarted.delete_presentation_session(world.id)
    assert restarted.get_presentation_session(world.id) is None
    restarted.close()
