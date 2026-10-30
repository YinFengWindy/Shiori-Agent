"""Host facts the scene plugin reads. Observation itself lives in the plugin."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from agent.core.passive_support import to_history_messages
from bootstrap.paths import REPOSITORY_ROOT, resource_root
from conversation.context_scope import history_filter, session_context_view
from core.roles.store import RoleStore
from session.manager import SessionManager
from shiori_sdk.core.scene import SceneHistoryMessage, SceneSubject


class HostSceneAdapter:
    """Role identity, follow-up demand, recent proactive history, publication.

    The proactive strategy flag stays on the host until proactive leaves.
    ``followup_wanted`` is that flag together with the role's own switch.
    One adapter serves one generation; ``publish`` marks it published.
    """

    def __init__(
        self,
        *,
        workspace: Path,
        roles: RoleStore,
        sessions: SessionManager,
        scene_followup: bool,
    ) -> None:
        self._workspace = workspace
        self._roles = roles
        self._sessions = sessions
        self._scene_followup = scene_followup
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

    def followup_wanted(self, role_id: str) -> bool:
        """Whether this role's scene follow-up is still a host strategy."""
        if not self._scene_followup:
            return False
        role = self._roles.get_role(role_id)
        return role is not None and role.proactive.enabled

    def proactive_history(
        self,
        *,
        session_key: str,
        role_id: str,
        thread_id: str,
        limit: int,
    ) -> tuple[SceneHistoryMessage, ...] | None:
        """Recent messages, or ``None`` when the turn is external context."""
        view = session_context_view(
            self._workspace,
            session_key=session_key,
            role_id=role_id,
            thread_id=thread_id,
        )
        if view is not None and view.is_external:
            return None
        session = self._sessions.get_or_create(session_key)
        messages = to_history_messages(
            session.history_window(limit, include=history_filter(view))
        )
        return tuple(
            SceneHistoryMessage(role=item.role, content=item.content)
            for item in messages
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
