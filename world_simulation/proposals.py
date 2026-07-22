"""Strict proposal contracts accepted by deterministic settlement."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from world_simulation.dependencies import DependencySet
from world_simulation.errors import InvalidWorldProposalError


@dataclass(frozen=True)
class ProposedEvent:
    """Candidate fact that has not yet entered the world timeline."""

    event_type: str
    effective_at: str
    participants: tuple[str, ...] = ()
    location: str = ""
    scope: str = "world"
    cause_event_ids: tuple[str, ...] = ()
    visibility: dict[str, Any] = field(default_factory=dict)
    changes: dict[str, Any] = field(default_factory=dict)
    dependencies: DependencySet = field(default_factory=DependencySet)
    is_backfill: bool = False


@dataclass(frozen=True)
class BeatProposal:
    """Versioned envelope for exactly one atomic narrative beat."""

    schema_version: int
    proposal_id: str
    proposal_type: str
    world_id: str
    world_revision: int
    run_id: str
    beat_sequence: int
    provider: str
    model: str
    prompt_version: str
    random_seed: str
    source: str
    events: tuple[ProposedEvent, ...]
    projection_patch: dict[str, Any] = field(default_factory=dict)
    cognition_patch: dict[str, dict[str, Any]] = field(default_factory=dict)
    barrier: dict[str, Any] | None = None
    scene_thread: dict[str, Any] | None = None
    performance_hint: dict[str, Any] | None = None

    def validate_envelope(self) -> None:
        """Fail closed when an adapter provides an unknown or incomplete envelope."""

        if self.schema_version != 1:
            raise InvalidWorldProposalError(
                f"unsupported proposal schema: {self.schema_version}"
            )
        required = {
            "proposal_id": self.proposal_id,
            "proposal_type": self.proposal_type,
            "world_id": self.world_id,
            "run_id": self.run_id,
            "provider": self.provider,
            "model": self.model,
            "prompt_version": self.prompt_version,
            "random_seed": self.random_seed,
            "source": self.source,
        }
        missing = [name for name, value in required.items() if not str(value).strip()]
        if missing:
            raise InvalidWorldProposalError(
                f"proposal missing required fields: {', '.join(missing)}"
            )
        if not self.events:
            raise InvalidWorldProposalError("proposal must contain at least one event")
