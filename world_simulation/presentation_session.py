"""Durable playback cursor for one world's derived presentation queue."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from world_simulation.world import utc_now

PresentationSessionStatus = Literal[
    "playing", "paused", "awaiting_action", "awaiting_barrier"
]
_SESSION_STATUSES = frozenset(
    ("playing", "paused", "awaiting_action", "awaiting_barrier")
)


@dataclass(frozen=True)
class WorldPresentationSession:
    """Persisted playback progress kept separate from authoritative world facts."""

    world_id: str
    last_presented_event_sequence: int = 0
    active_plan_id: str | None = None
    active_cue_index: int = 0
    status: PresentationSessionStatus = "awaiting_action"
    updated_at: str = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        """Reject invalid cursors before they are written to SQLite."""

        self.validate()

    def validate(self) -> None:
        """Validate session identity, cursor bounds, and lifecycle status."""

        if not self.world_id.strip():
            raise ValueError("world_id is required")
        if self.last_presented_event_sequence < 0:
            raise ValueError("last_presented_event_sequence must be non-negative")
        if self.active_cue_index < 0:
            raise ValueError("active_cue_index must be non-negative")
        if self.active_plan_id is not None and not self.active_plan_id.strip():
            raise ValueError("active_plan_id cannot be empty")
        if self.status not in _SESSION_STATUSES:
            raise ValueError(f"unsupported presentation session status: {self.status}")
        if not self.updated_at.strip():
            raise ValueError("updated_at is required")

    def to_dict(self) -> dict[str, Any]:
        """Serialize the internal snake_case session record."""

        return asdict(self)

    def to_bridge_dict(self) -> dict[str, Any]:
        """Serialize the session envelope exposed to the renderer."""

        return {
            "worldId": self.world_id,
            "lastPresentedEventSequence": self.last_presented_event_sequence,
            "activePlanId": self.active_plan_id,
            "activeCueIndex": self.active_cue_index,
            "status": self.status,
            "updatedAt": self.updated_at,
        }
