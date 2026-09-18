from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

from infra.persistence.json_store import atomic_save_json, load_json

from .models import RoleRecord
from .migration import CURRENT_MANIFEST_VERSION, migrate_manifest_payload

MANIFEST_VERSION = CURRENT_MANIFEST_VERSION
_LOCKS: dict[Path, Any] = {}
_LOCKS_GUARD = threading.Lock()


def _manifest_lock(path: Path):
    # Every repository instance addressing the same canonical file participates
    # in the same process-local read/modify/write transaction.
    with _LOCKS_GUARD:
        return _LOCKS.setdefault(path.resolve(), threading.RLock())


class RoleManifestRepository:
    """Owns the versioned role manifest, migration, and process-local lock."""

    def __init__(self, workspace: Path) -> None:
        self.roles_dir = workspace / "roles"
        self.assets_dir = self.roles_dir / "assets"
        self.manifest_path = self.roles_dir / "roles.json"
        self.lock = _manifest_lock(self.manifest_path)
        self._ensure_layout()

    def list_roles(self) -> list[RoleRecord]:
        with self.lock:
            payload = self.load_payload()
            roles = [RoleRecord.from_dict(item) for item in payload["roles"]]
        return sorted(roles, key=lambda item: (item.updated_at, item.id), reverse=True)

    def get_role(self, role_id: str) -> RoleRecord | None:
        role_id = str(role_id).strip()
        if not role_id:
            return None
        return next((role for role in self.list_roles() if role.id == role_id), None)

    def load_payload(self) -> dict[str, Any]:
        """Reads and upgrades under the same lock used by all manifest writers."""
        with self.lock:
            return self._load_payload()

    def _load_payload(self) -> dict[str, Any]:
        payload = load_json(
            self.manifest_path,
            default={"version": MANIFEST_VERSION, "roles": []},
            domain="roles",
        )
        if not isinstance(payload, dict):
            raise ValueError("角色清单格式无效：根节点必须是对象")
        roles = payload.get("roles")
        if not isinstance(roles, list):
            raise ValueError("角色清单格式无效：roles 必须是数组")
        for item in roles:
            if not isinstance(item, dict):
                raise ValueError("角色清单格式无效：角色记录必须是对象")
        migrated, changed = migrate_manifest_payload(payload)
        if changed:
            # Persist once so future reads do not repeatedly perform the migration.
            atomic_save_json(self.manifest_path, migrated, domain="roles")
        return migrated

    def save_roles(
        self, roles: list[RoleRecord], *, plugin_data: dict[str, Any] | None = None
    ) -> None:
        """Commits role snapshots and optional opaque plugin state together."""
        self.save_payload([role.to_dict() for role in roles], plugin_data=plugin_data)

    def save_payload(
        self, roles: list[dict[str, Any]], *, plugin_data: dict[str, Any] | None = None
    ) -> None:
        """Preserves plugin namespaces on every ordinary role rewrite."""
        with self.lock:
            # Loading/migrating first prevents a disabled plugin's legacy fields
            # from being discarded by a stale RoleRecord projection.
            payload = self.load_payload() if self.manifest_path.exists() else {}
            payload.update(version=MANIFEST_VERSION, roles=roles)
            if plugin_data is not None:
                payload["plugin_data"] = plugin_data
            payload, _ = migrate_manifest_payload(payload)
            atomic_save_json(self.manifest_path, payload, domain="roles")

    def _ensure_layout(self) -> None:
        self.roles_dir.mkdir(parents=True, exist_ok=True)
        self.assets_dir.mkdir(parents=True, exist_ok=True)
        with self.lock:
            if not self.manifest_path.exists():
                self.save_roles([])
