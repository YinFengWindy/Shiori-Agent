"""Host facts the scene plugin reads. Observation itself lives in the plugin."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from bootstrap.paths import REPOSITORY_ROOT, resource_root
from core.roles.store import RoleStore
from session.manager import SessionManager
from shiori_sdk.core.scene import SceneSubject


class HostSceneAdapter:
    """Role identity and publication.

    One adapter serves one generation; ``publish`` marks it published.
    Scene follow-up demand is ``SCENE.request`` from the proactive plugin.
    """

    def __init__(
        self,
        *,
        workspace: Path,
        roles: RoleStore,
        sessions: SessionManager,
    ) -> None:
        self._workspace = workspace
        self._roles = roles
        self._sessions = sessions
        self._published = False
        self._starts: dict[object, Callable[[], None]] = {}

    def subject(self, session_key: str, role_id: str) -> SceneSubject | None:
        """The role of this turn, from ``role_id`` or the session."""
        session = self._sessions.get_or_create(session_key)
        clean = str(role_id or session.metadata.get("role_id") or "").strip()
        if not clean:
            return None
        role = self._roles.get_role(clean)
        if role is None:
            return None
        return SceneSubject(
            id=role.id,
            name=role.name or role.id,
            system_prompt=role.system_prompt,
        )

    def on_published(self, start: Callable[[], None]) -> Callable[[], None]:
        """Runs ``start`` at publication, or now in a published generation."""
        if self._published:
            start()
            return lambda: None
        key = object()
        self._starts[key] = start

        def dispose() -> None:
            self._starts.pop(key, None)

        return dispose

    def publish(self) -> None:
        """Marks the generation published and runs the waiting starts once."""
        if self._published:
            return
        self._published = True
        starts = tuple(self._starts.values())
        self._starts.clear()
        for start in starts:
            start()

    def legacy_state_paths(self) -> tuple[Path, ...]:
        """Roots a first live write may import ``scene_awareness`` state from."""
        return (
            resource_root() / "plugins",
            REPOSITORY_ROOT / "apps" / "backend" / "plugins",
        )
