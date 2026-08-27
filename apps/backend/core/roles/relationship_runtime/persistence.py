"""角色关系快照与寂寞状态的 JSON 持久化。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from infra.persistence.json_store import atomic_save_json, load_json

_SNAPSHOT_FILE = "relationship_snapshot.json"
_RUNTIME_FILE = "loneliness_runtime.json"

class _RelationshipPersistenceMixin:
    def state_root(self, role_id: str) -> Path:
        return self._workspace / "roles" / str(role_id).strip() / "state"

    def snapshot_path(self, role_id: str) -> Path:
        return self.state_root(role_id) / _SNAPSHOT_FILE

    def runtime_path(self, role_id: str) -> Path:
        return self.state_root(role_id) / _RUNTIME_FILE

    def read_snapshot(self, role_id: str) -> dict[str, Any] | None:
        payload = load_json(self.snapshot_path(role_id), default=None, domain="role.relationship")
        if not isinstance(payload, dict):
            return None
        return self._normalize_snapshot_payload(role_id=role_id, payload=payload, preserve_error=True)

    def read_loneliness_runtime(self, role_id: str) -> dict[str, Any] | None:
        payload = load_json(self.runtime_path(role_id), default=None, domain="role.loneliness")
        if not isinstance(payload, dict):
            return None
        return self._normalize_runtime_payload(role_id=role_id, payload=payload)

    def write_snapshot(self, role_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        normalized = self._normalize_snapshot_payload(role_id=role_id, payload=payload, preserve_error=True)
        path = self.snapshot_path(role_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_save_json(path, normalized, domain="role.relationship")
        return normalized

    def write_loneliness_runtime(self, role_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        normalized = self._normalize_runtime_payload(role_id=role_id, payload=payload)
        path = self.runtime_path(role_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_save_json(path, normalized, domain="role.loneliness")
        return normalized
