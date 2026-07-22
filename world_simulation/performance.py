"""Replaceable presentation plans derived from committed world facts."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class PerformancePlan:
    """Presentation-only instructions that cannot alter world facts."""

    id: str
    world_id: str
    event_id: str
    dialogue: dict[str, Any] | None = None
    sprites: tuple[dict[str, Any], ...] = ()
    background: dict[str, Any] | None = None
    camera: tuple[dict[str, Any], ...] = ()
    audio: tuple[dict[str, Any], ...] = ()
    cg_tasks: tuple[dict[str, Any], ...] = ()
    fallback_text: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialize the replaceable performance plan."""

        return asdict(self)
