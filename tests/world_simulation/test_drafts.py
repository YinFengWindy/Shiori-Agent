import pytest

from world_simulation.drafts import create_world_draft
from world_simulation.world import NativeResident, RoleTemplateSnapshot, WorldTemplate


def _snapshot() -> RoleTemplateSnapshot:
    return RoleTemplateSnapshot(
        id="snapshot-rin",
        source_role_id="rin",
        source_version="v1",
        persona={"temperament": "calm"},
    )


def _resident(snapshot_id: str) -> NativeResident:
    return NativeResident(
        id="resident-rin",
        snapshot_id=snapshot_id,
        name="Rin",
        occupation="student",
        residence="dorm",
    )


def test_create_world_draft_preserves_metadata_and_accepts_explicit_id():
    snapshot = _snapshot()
    metadata = {"input": {"seed": "rain-harbor"}}

    draft = create_world_draft(
        owner_id="player-1",
        template=WorldTemplate(id="template-1", name="Rain Harbor", era="modern"),
        role_snapshots=(snapshot,),
        residents=(_resident(snapshot.id),),
        initial_time="2026-07-31T08:00:00+00:00",
        creation_metadata=metadata,
        draft_id="draft-1",
    )

    assert draft.id == "draft-1"
    assert draft.creation_metadata == metadata
    assert draft.role_snapshots == (snapshot,)
    assert draft.residents == (_resident(snapshot.id),)


def test_create_world_draft_rejects_resident_from_unknown_snapshot():
    with pytest.raises(ValueError, match="every resident"):
        create_world_draft(
            owner_id="player-1",
            template=WorldTemplate(id="template-1", name="Rain Harbor", era="modern"),
            role_snapshots=(_snapshot(),),
            residents=(_resident("snapshot-missing"),),
            initial_time="2026-07-31T08:00:00+00:00",
        )
