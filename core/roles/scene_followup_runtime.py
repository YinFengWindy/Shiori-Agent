from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal

from infra.persistence.json_store import atomic_save_json, load_json

_FOLLOWUP_DELAYS_MINUTES = (5, 3, 1)
_MAX_SCENE_LIFETIME = timedelta(hours=1)
_STATE_FILE = "scene_followup_runtime.json"
SceneTransition = Literal["started", "same", "changed", "closed"]


def _now_utc(value: datetime | None = None) -> datetime:
    current = value or datetime.now(timezone.utc)
    if current.tzinfo is None:
        return current.replace(tzinfo=timezone.utc)
    return current.astimezone(timezone.utc)


def _parse_timestamp(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return _now_utc(parsed)


class SceneFollowupRuntime:
    """Persists short-lived same-scene follow-up scheduling per role."""

    def __init__(self, workspace: Path) -> None:
        self._workspace = Path(workspace)

    def handle_user_message(
        self,
        session_key: str,
        *,
        now: datetime | None = None,
    ) -> dict[str, Any] | None:
        """Starts a fresh follow-up chain from the latest user interaction."""
        role_id = self._role_id_from_session_key(session_key)
        if not role_id:
            return None
        current = _now_utc(now)
        previous = self._read(role_id) or {}
        state = self._build_state(
            role_id,
            anchor_at=current,
            attempt_index=0,
            next_due_at=current + timedelta(minutes=_FOLLOWUP_DELAYS_MINUTES[0]),
            expires_at=current + _MAX_SCENE_LIFETIME,
            scene_key=str(previous.get("scene_key") or ""),
        )
        return self._write(role_id, state)

    def apply_scene_decision(
        self,
        session_key: str,
        scene_transition: SceneTransition,
        scene_key: str = "",
        *,
        now: datetime | None = None,
    ) -> dict[str, Any] | None:
        """Updates the active follow-up scene from a shared turn decision."""
        role_id = self._role_id_from_session_key(session_key)
        if not role_id:
            return None
        if scene_transition in {"changed", "closed"}:
            self.close(session_key)
            return None
        state = self._read(role_id)
        if state is None:
            return None
        updated = dict(state)
        clean_scene_key = str(scene_key or "").strip()
        if clean_scene_key:
            updated["scene_key"] = clean_scene_key
        current = _now_utc(now)
        expires_at = _parse_timestamp(updated.get("expires_at"))
        if expires_at is None or expires_at <= current:
            self.close(session_key)
            return None
        return self._write(role_id, updated)

    def should_trigger(
        self,
        session_key: str,
        now: datetime | None = None,
    ) -> tuple[bool, dict[str, Any]]:
        """Returns whether the next same-scene follow-up is due."""
        role_id = self._role_id_from_session_key(session_key)
        if not role_id:
            return False, {"reason": "no_role"}
        state = self._read(role_id)
        if state is None:
            return False, {"reason": "no_scene"}
        current = _now_utc(now)
        expires_at = _parse_timestamp(state.get("expires_at"))
        if expires_at is None or expires_at <= current:
            self.close(session_key)
            return False, {"reason": "expired"}
        next_due_at = _parse_timestamp(state.get("next_due_at"))
        if next_due_at is None or next_due_at > current:
            return False, {
                "reason": "not_due",
                "next_due_at": state.get("next_due_at", ""),
                "attempt_index": state.get("attempt_index", 0),
            }
        return True, {
            "reason": "scene_followup_due",
            "attempt_index": int(state.get("attempt_index", 0) or 0),
            "anchor_at": state.get("anchor_at", ""),
            "expires_at": state.get("expires_at", ""),
        }

    def handle_followup_sent(
        self,
        session_key: str,
        *,
        now: datetime | None = None,
    ) -> dict[str, Any] | None:
        """Advances the schedule after a follow-up was delivered successfully."""
        role_id = self._role_id_from_session_key(session_key)
        if not role_id:
            return None
        state = self._read(role_id)
        if state is None:
            return None
        attempt_index = int(state.get("attempt_index", 0) or 0)
        if attempt_index >= len(_FOLLOWUP_DELAYS_MINUTES) - 1:
            self.close(session_key)
            return None
        current = _now_utc(now)
        expires_at = _parse_timestamp(state.get("expires_at"))
        if expires_at is None or expires_at <= current:
            self.close(session_key)
            return None
        next_attempt = attempt_index + 1
        updated = dict(state)
        updated["attempt_index"] = next_attempt
        updated["next_due_at"] = (
            current + timedelta(minutes=_FOLLOWUP_DELAYS_MINUTES[next_attempt])
        ).isoformat()
        return self._write(role_id, updated)

    def close(self, session_key: str) -> None:
        """Closes the current scene so later proactive turns use loneliness."""
        role_id = self._role_id_from_session_key(session_key)
        if not role_id:
            return
        self._state_path(role_id).unlink(missing_ok=True)

    def read(self, session_key: str) -> dict[str, Any] | None:
        """Reads the persisted scene follow-up state for a role session."""
        role_id = self._role_id_from_session_key(session_key)
        return self._read(role_id) if role_id else None

    def _state_path(self, role_id: str) -> Path:
        return self._workspace / "roles" / role_id / "state" / _STATE_FILE

    def _read(self, role_id: str) -> dict[str, Any] | None:
        payload = load_json(self._state_path(role_id), default=None, domain="role.scene_followup")
        if not isinstance(payload, dict):
            return None
        return payload

    def _write(self, role_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        normalized = {
            "role_id": role_id,
            "anchor_at": str(payload.get("anchor_at") or ""),
            "next_due_at": str(payload.get("next_due_at") or ""),
            "attempt_index": max(
                0,
                min(
                    len(_FOLLOWUP_DELAYS_MINUTES),
                    int(payload.get("attempt_index", 0) or 0),
                ),
            ),
            "scene_key": str(payload.get("scene_key") or "").strip(),
            "expires_at": str(payload.get("expires_at") or ""),
        }
        atomic_save_json(
            self._state_path(role_id),
            normalized,
            domain="role.scene_followup",
        )
        return normalized

    @staticmethod
    def _build_state(
        role_id: str,
        *,
        anchor_at: datetime,
        attempt_index: int,
        next_due_at: datetime,
        expires_at: datetime,
        scene_key: str = "",
    ) -> dict[str, Any]:
        return {
            "role_id": role_id,
            "anchor_at": anchor_at.isoformat(),
            "next_due_at": next_due_at.isoformat(),
            "attempt_index": attempt_index,
            "scene_key": scene_key,
            "expires_at": expires_at.isoformat(),
        }

    @staticmethod
    def _role_id_from_session_key(session_key: str) -> str:
        clean_key = str(session_key or "").strip()
        if clean_key.startswith("role:"):
            return clean_key.split(":", 1)[1]
        return ""
