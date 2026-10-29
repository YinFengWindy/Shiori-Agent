"""``SCENE`` and ``SCENE_HOST``: demand-driven scene observation (P6a, D7).

Observation is not on the turn's critical path, so it stays a plugin. The
``scene`` plugin provides ``SCENE``. The host provides ``SCENE_HOST``: role
identity, whether the host still wants a scene follow-up, and recent proactive
history. ``None`` from ``get(SCENE)`` means observation is off; chat still runs.

``request`` returns a disposer. The caller effects it so demand leaves with
the caller. The host calls ``activate`` when the generation is published and
``close`` before that generation is dropped.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from shiori_sdk.kernel import Key
from shiori_sdk.roles import RoleView


@dataclass(frozen=True)
class SceneSubject:
    """The role a scene observation is about."""

    id: str
    name: str
    system_prompt: str


@dataclass(frozen=True)
class SceneHistoryMessage:
    """One recent message, already limited to the user's own context."""

    role: str
    content: str


class SceneHost(Protocol):
    """Host facts the scene plugin cannot import."""

    def subject(self, session_key: str, role_id: str) -> SceneSubject | None:
        """The role of this turn, from ``role_id`` or the session. None if absent."""
        ...

    def followup_wanted(self, role_id: str) -> bool:
        """Whether the host's scene-follow-up strategy applies to this role.

        The proactive strategy flag stays on the host until proactive leaves.
        This is not a method on ``Roles``.
        """
        ...

    def proactive_history(
        self,
        *,
        session_key: str,
        role_id: str,
        thread_id: str,
        limit: int,
    ) -> tuple[SceneHistoryMessage, ...] | None:
        """Recent messages for a proactive turn.

        ``None`` means the turn is external context and must not be observed.
        """
        ...

    def legacy_state_paths(self) -> tuple[Path, ...]:
        """Extra files a first live write may import scene state from."""
        ...


class Scene(Protocol):
    """The scene plugin's observation service."""

    def request(self, predicate: Callable[[RoleView], bool]) -> Callable[[], None]:
        """Register demand and return the disposer that drops it.

        The predicate sees a role view. Demand does not start observation.
        """
        ...

    def activate(self) -> None:
        """Start intake. Repeated calls do nothing."""
        ...

    async def close(self) -> None:
        """Stop intake and wait for in-flight observations."""
        ...


SCENE: Key[Scene] = Key("scene")
"""Scene observation. The scene plugin provides this; the host never does."""

SCENE_HOST: Key[SceneHost] = Key("scene_host")
"""Host facts for the scene plugin. The host provides this."""
