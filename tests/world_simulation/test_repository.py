from world_simulation.repository import WorldRepository


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
