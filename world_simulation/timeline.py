"""Immutable timeline facts and current-state projection models."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from world_simulation.dependencies import DependencySet
from world_simulation.world import utc_now


@dataclass(frozen=True)
class TimelineEvent:
    """One append-only world fact with separate effective and write ordering."""

    id: str
    world_id: str
    event_type: str
    effective_at: str
    sequence: int
    participants: tuple[str, ...] = ()
    location: str = ""
    scope: str = "world"
    cause_event_ids: tuple[str, ...] = ()
    visibility: dict[str, Any] = field(default_factory=dict)
    changes: dict[str, Any] = field(default_factory=dict)
    random_ref: str = ""
    is_backfill: bool = False
    request_id: str = ""
    committed_revision: int = 0
    dependencies: DependencySet = field(default_factory=DependencySet)
    recorded_at: str = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the event including dependency metadata."""

        payload = asdict(self)
        payload["dependencies"] = self.dependencies.to_dict()
        return payload


@dataclass(frozen=True)
class WorldStateProjection:
    """Rebuildable current state derived from committed timeline events."""

    world_id: str
    revision: int
    state: dict[str, Any] = field(default_factory=dict)
    cognition: dict[str, dict[str, Any]] = field(default_factory=dict)
    invalid_after: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize the projection."""

        return asdict(self)
