from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

from infra.persistence.json_store import atomic_save_json, load_json

from .models import DEFAULT_ASSET_CATEGORY_ID, RoleRecord, default_asset_category

MANIFEST_VERSION = 2


class RoleManifestRepository:
    """Owns the versioned role manifest, migration, and process-local lock."""

    def __init__(self, workspace: Path) -> None:
        self.roles_dir = workspace / "roles"
        self.assets_dir = self.roles_dir / "assets"
        self.manifest_path = self.roles_dir / "roles.json"
        self.lock = threading.RLock()
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
        migrated = False
        normalized_roles: list[dict[str, Any]] = []
        for item in roles:
            if not isinstance(item, dict):
                raise ValueError("角色清单格式无效：角色记录必须是对象")
            role_payload = dict(item)
            if "featured_image" in role_payload:
                if "chat_background" not in role_payload:
                    role_payload["chat_background"] = role_payload.get("featured_image")
                del role_payload["featured_image"]
                migrated = True
            if not isinstance(role_payload.get("asset_categories"), list):
                role_payload["asset_categories"] = [default_asset_category().to_dict()]
                migrated = True
            if not isinstance(role_payload.get("asset_category_bindings"), dict):
                raw_categories = role_payload.get("asset_categories")
                first_category_id = (
                    str(raw_categories[0].get("id") or "").strip()
                    if isinstance(raw_categories, list)
                    and raw_categories
                    and isinstance(raw_categories[0], dict)
                    else DEFAULT_ASSET_CATEGORY_ID
                )
                role_payload["asset_category_bindings"] = {
                    str(path): first_category_id
                    for path in role_payload.get("illustrations", [])
                    if str(path).strip()
                }
                migrated = True
            normalized_roles.append(role_payload)
        if migrated:
            self.save_payload(normalized_roles)
        return {
            "version": max(
                int(payload.get("version") or MANIFEST_VERSION),
                MANIFEST_VERSION,
            ),
            "roles": normalized_roles,
        }

    def save_roles(self, roles: list[RoleRecord]) -> None:
        self.save_payload([role.to_dict() for role in roles])

    def save_payload(self, roles: list[dict[str, Any]]) -> None:
        atomic_save_json(
            self.manifest_path,
            {"version": MANIFEST_VERSION, "roles": roles},
            domain="roles",
        )

    def _ensure_layout(self) -> None:
        self.roles_dir.mkdir(parents=True, exist_ok=True)
        self.assets_dir.mkdir(parents=True, exist_ok=True)
        if not self.manifest_path.exists():
            self.save_roles([])
