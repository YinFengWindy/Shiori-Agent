"""World templates, immutable role snapshots, and world identity models."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


def utc_now() -> str:
    """Return an ISO timestamp suitable for persisted domain records."""

    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class WorldTemplate:
    """Reusable rules used to create a world, not mutable runtime state."""

    id: str
    name: str
    era: str
    locations: tuple[str, ...] = ()
    social_structure: dict[str, Any] = field(default_factory=dict)
    ability_system: dict[str, Any] = field(default_factory=dict)
    prohibitions: tuple[str, ...] = ()
    initial_environment: dict[str, Any] = field(default_factory=dict)
    narrative_style: str = ""
    initial_pressures: tuple[dict[str, Any], ...] = ()
    version: int = 1

    def to_dict(self) -> dict[str, Any]:
        """Serialize the template without retaining mutable aliases."""

        return asdict(self)


@dataclass(frozen=True)
class RoleTemplateSnapshot:
    """Immutable world-owned capture of a role and its referenced assets."""

    id: str
    source_role_id: str
    source_version: str
    persona: dict[str, Any]
    system_constraints: tuple[str, ...] = ()
    visual_profile: dict[str, Any] = field(default_factory=dict)
    assets: tuple[dict[str, Any], ...] = ()
    schema_version: int = 1
    created_at: str = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the immutable snapshot for storage or transfer."""

        return asdict(self)


@dataclass(frozen=True)
class NativeResident:
    """A role snapshot adapted into one world's private native identity."""

    id: str
    snapshot_id: str
    name: str
    origin: str = ""
    occupation: str = ""
    residence: str = ""
    social_position: str = ""
    initial_relationships: dict[str, Any] = field(default_factory=dict)
    prior_experiences: tuple[dict[str, Any], ...] = ()
    core_persona_facts: tuple[str, ...] = ()
    visual_identity: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the resident identity."""

        return asdict(self)


@dataclass(frozen=True)
class WorldDraft:
    """Reviewable creation proposal that is not yet a source of world facts."""

    id: str
    owner_id: str
    template: WorldTemplate
    role_snapshots: tuple[RoleTemplateSnapshot, ...]
    residents: tuple[NativeResident, ...]
    initial_time: str
    creation_metadata: dict[str, Any] = field(default_factory=dict)
    status: str = "draft"
    created_at: str = field(default_factory=utc_now)


@dataclass(frozen=True)
class WorldInstance:
    """Persistent owner of one shared clock and one continuing main timeline."""

    id: str
    owner_id: str
    template_snapshot: dict[str, Any]
    current_time: str
    revision: int = 0
    active_oc_id: str | None = None
    parent_world_id: str | None = None
    fork_event_id: str | None = None
    random_state: str = ""
    created_at: str = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the world instance."""

        return asdict(self)
