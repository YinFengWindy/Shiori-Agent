from pathlib import Path

import pytest

from world_simulation.repository import WorldRepository
from world_simulation.service import WorldSimulationService
from world_simulation.world import (
    NativeResident,
    RoleTemplateSnapshot,
    WorldTemplate,
)


@pytest.fixture
def repository(tmp_path: Path):
    value = WorldRepository(tmp_path / "worlds.db")
    yield value
    value.close()


@pytest.fixture
def service(repository: WorldRepository):
    return WorldSimulationService(repository)


@pytest.fixture
def world(service: WorldSimulationService):
    snapshot = RoleTemplateSnapshot(
        id="snapshot-rin",
        source_role_id="rin",
        source_version="v1",
        persona={"temperament": "calm"},
    )
    draft = service.create_draft(
        owner_id="player-1",
        template=WorldTemplate(
            id="template-school",
            name="School",
            era="modern",
            locations=("classroom", "library"),
        ),
        role_snapshots=(snapshot,),
        residents=(
            NativeResident(
                id="resident-rin",
                snapshot_id=snapshot.id,
                name="Rin",
                occupation="student",
                residence="dorm",
            ),
        ),
        initial_time="2026-04-01T08:00:00+00:00",
        draft_id="draft-1",
    )
    return service.confirm_world(
        draft.id,
        request_id="confirm-1",
        world_id="world-1",
        random_seed="seed-initial",
    )
