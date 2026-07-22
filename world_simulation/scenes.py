"""Scene opportunities and player decision barriers."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from world_simulation.world import utc_now

SceneControl = Literal["auto", "optional", "required"]


@dataclass(frozen=True)
class DecisionBarrier:
    """A world-time boundary that deterministic progression cannot cross."""

    id: str
    world_id: str
    effective_at: str
    oc_id: str
    reason: str
    options: tuple[dict[str, Any], ...] = ()
    status: str = "pending"
    resolution: dict[str, Any] | None = None
    created_at: str = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the barrier."""

        return asdict(self)


@dataclass(frozen=True)
class SceneThread:
    """Rebuildable read model for committed beats in one world scene."""

    id: str
    world_id: str
    world_time: str
    location: str
    participants: dict[str, str]
    active_oc_id: str
    beat_sequence: int = 0
    status: str = "active"
    stop_reason: str = ""
    barrier_id: str | None = None
    messages: tuple[dict[str, Any], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        """Serialize the scene read model."""

        return asdict(self)
