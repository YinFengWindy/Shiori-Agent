from world_simulation.catalog import WorldCatalog
from world_simulation.drafts import create_world_draft
from world_simulation.world import NativeResident, RoleTemplateSnapshot, WorldTemplate


def test_catalog_persists_drafts_world_summaries_and_idempotency(tmp_path):
    catalog = WorldCatalog(tmp_path / "worlds" / "catalog.db")
    snapshot = RoleTemplateSnapshot(
        id="snapshot-rin",
        source_role_id="rin",
        source_version="v1",
        persona={"temperament": "calm"},
    )
    draft = create_world_draft(
        owner_id="player-1",
        template=WorldTemplate(id="template-1", name="雨港", era="modern"),
        role_snapshots=(snapshot,),
        residents=(
            NativeResident(
                id="resident-rin",
                snapshot_id=snapshot.id,
                name="凛",
                occupation="student",
                residence="dorm",
            ),
        ),
        initial_time="2026-07-31T08:00:00+00:00",
        draft_id="draft-1",
    )
    catalog.save_draft(draft)
    restored = catalog.get_draft(draft.id)
    assert restored is not None
    assert restored.id == draft.id
    assert restored.template.name == draft.template.name
    assert restored.role_snapshots[0].source_role_id == "rin"
    assert restored.residents[0].name == "凛"

    summary = {
        "id": "world-1",
        "name": "雨港",
        "currentDayIndex": 1,
        "status": "action_required",
    }
    catalog.complete_world(
        draft_id=draft.id,
        world_id="world-1",
        relative_db_path="world-1/world.db",
        summary=summary,
        request_id="confirm-1",
    )
    assert catalog.world_id_for_request("confirm-1") == "world-1"
    assert catalog.relative_db_path("world-1") == "world-1/world.db"
    assert catalog.list_summaries() == [summary]
    assert catalog.get_draft(draft.id).status == "confirmed"

    updated = {**summary, "currentDayIndex": 2}
    catalog.update_summary("world-1", updated)
    assert catalog.list_summaries() == [updated]
    catalog.close()
