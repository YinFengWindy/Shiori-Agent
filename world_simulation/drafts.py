"""Draft construction shared by world application boundaries."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from world_simulation.world import (
    NativeResident,
    RoleTemplateSnapshot,
    WorldDraft,
    WorldTemplate,
)


def create_world_draft(
    *,
    owner_id: str,
    template: WorldTemplate,
    role_snapshots: tuple[RoleTemplateSnapshot, ...],
    residents: tuple[NativeResident, ...],
    initial_time: str,
    creation_metadata: dict[str, Any] | None = None,
    draft_id: str | None = None,
) -> WorldDraft:
    """Build and validate a reviewable draft without choosing its storage."""

    snapshot_ids = {item.id for item in role_snapshots}
    if any(item.snapshot_id not in snapshot_ids for item in residents):
        raise ValueError("every resident must reference a snapshot in the draft")
    return WorldDraft(
        id=draft_id or f"draft-{uuid4().hex}",
        owner_id=owner_id,
        template=template,
        role_snapshots=role_snapshots,
        residents=residents,
        initial_time=initial_time,
        creation_metadata=dict(creation_metadata or {}),
    )
