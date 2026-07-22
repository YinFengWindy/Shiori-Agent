"""World-owned actor and cognition models."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class AutonomyPolicy:
    """Defines which low-risk choices an uncontrolled OC may make."""

    allowed_actions: tuple[str, ...] = ()
    risk_boundaries: tuple[str, ...] = ()
    allow_optional_scenes: bool = False


@dataclass(frozen=True)
class PlayerOC:
    """One player-controlled identity sharing a world's objective facts."""

    id: str
    name: str
    persona: dict[str, Any]
    identity: dict[str, Any]
    visual_profile: dict[str, Any] = field(default_factory=dict)
    primary_goal: str = ""
    behavior_constraints: tuple[str, ...] = ()
    autonomy: AutonomyPolicy = field(default_factory=AutonomyPolicy)
    location: str = ""
    relationships: dict[str, Any] = field(default_factory=dict)
    abilities: dict[str, Any] = field(default_factory=dict)
    status: dict[str, Any] = field(default_factory=dict)
    resources: dict[str, Any] = field(default_factory=dict)
    cognition: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize OC state into an isolated value."""

        return asdict(self)
