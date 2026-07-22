"""Persistent world-run state machine."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from typing import Any

from world_simulation.errors import InvalidRunTransitionError
from world_simulation.world import utc_now

_TRANSITIONS = {
    "queued": {"running", "cancelled", "failed"},
    "running": {"settling", "cancelled", "failed", "completed"},
    "settling": {"committed", "cancelled", "failed"},
    "committed": {"presenting", "running", "completed", "cancelled"},
    "presenting": {"running", "completed", "cancelled", "failed"},
    "completed": set(),
    "failed": set(),
    "cancelled": set(),
}


@dataclass(frozen=True)
class WorldRun:
    """Recoverable execution record for one world command."""

    id: str
    request_id: str
    world_id: str
    kind: str
    starting_revision: int
    random_seed: str
    status: str = "queued"
    last_committed_revision: int | None = None
    error: dict[str, Any] | None = None
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)

    def transition(self, status: str, **changes: Any) -> "WorldRun":
        """Return a validated next state without mutating this run."""

        if status not in _TRANSITIONS.get(self.status, set()):
            raise InvalidRunTransitionError(
                f"invalid world run transition: {self.status} -> {status}"
            )
        return replace(self, status=status, updated_at=utc_now(), **changes)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the run."""

        return asdict(self)
