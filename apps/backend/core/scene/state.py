"""Durable core scene state, with read-only preparation of legacy migration."""

from pathlib import Path
from typing import Any

from core.scene.contracts import SceneDecision
from shiori_sdk.files.json import atomic_save_json, load_json

_STATE_KEY = "scene_awareness_sessions"


class SceneStateStore:
    """Reads current state on each access; first live write imports legacy state once.

    Candidate construction never writes. A closed scene persists an empty map, so
    stale legacy data cannot resurrect it on subsequent generations or restarts.
    """

    def __init__(self, workspace: Path, legacy_roots: tuple[Path, ...] = ()) -> None:
        self._revisions: dict[str, int] = {}
        self.path = workspace / "scene" / "state.json"
        self._sources = (
            workspace / "plugins" / "scene_awareness" / "kv.json",
        ) + tuple(root / "scene_awareness" / ".kv.json" for root in legacy_roots)
        self._read()  # Invalid persisted state rejects candidate preparation early.

    def reserve(self, session_key: str) -> int:
        """Orders accepted observations across generations sharing this state owner."""
        revision = self._revisions.get(session_key, 0) + 1
        self._revisions[session_key] = revision
        return revision

    def is_current(self, session_key: str, revision: int) -> bool:
        """Prevents an older model result overwriting a newer same-session snapshot."""
        return self._revisions.get(session_key, 0) == revision

    def _read(self) -> dict[str, Any]:
        source = (
            self.path
            if self.path.exists()
            else next((path for path in self._sources if path.exists()), None)
        )
        data = load_json(source, {}) if source is not None else {}
        if not isinstance(data, dict):
            raise ValueError("场景状态必须是 JSON 对象")
        return data

    def get(self, key: str, default: Any = None) -> Any:
        """Reads state without mutating live storage during preparation."""
        return self._read().get(key, default)

    def set(self, key: str, value: Any) -> None:
        """Atomically imports legacy keys and saves a live scene update."""
        data = self._read()
        data[key] = value
        atomic_save_json(self.path, data)

    def current(self, session_key: str) -> dict[str, str]:
        """Returns the most recently committed scene and visual identity."""
        raw = self.get(_STATE_KEY, {})
        state = raw.get(session_key) if isinstance(raw, dict) else None
        if not isinstance(state, dict):
            return {"scene_key": "", "visual_key": ""}
        return {
            key: str(state.get(key) or "").strip()
            for key in ("scene_key", "visual_key")
        }

    def apply(self, session_key: str, decision: SceneDecision) -> None:
        """Persists a transition while retaining other sessions and migrated keys."""
        raw = self.get(_STATE_KEY, {})
        sessions = dict(raw) if isinstance(raw, dict) else {}
        if decision.transition == "closed":
            sessions.pop(session_key, None)
        elif decision.scene_key:
            sessions[session_key] = {
                "scene_key": decision.scene_key,
                "visual_key": decision.visual_key,
            }
        self.set(_STATE_KEY, sessions)
