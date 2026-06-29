from __future__ import annotations

import shutil
import threading
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from infra.persistence.json_store import atomic_save_json, load_json

_MANIFEST_VERSION = 1


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat()


def _normalize_rel_path(path: str | None) -> str | None:
    if not path:
        return None
    return path.replace("\\", "/")


@dataclass
class RoleRecord:
    """角色聚合根的持久化快照。"""

    id: str
    name: str
    description: str
    system_prompt: str
    background: str
    avatar: str | None
    illustrations: list[str]
    runtime_config: dict[str, Any]
    memory_init_state: dict[str, Any]
    created_at: str
    updated_at: str

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["avatar"] = _normalize_rel_path(self.avatar)
        payload["illustrations"] = [
            _normalize_rel_path(path) or "" for path in self.illustrations
        ]
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RoleRecord":
        return cls(
            id=str(payload.get("id") or "").strip(),
            name=str(payload.get("name") or "").strip(),
            description=str(payload.get("description") or ""),
            system_prompt=str(payload.get("system_prompt") or ""),
            background=str(payload.get("background") or ""),
            avatar=_normalize_rel_path(payload.get("avatar")),
            illustrations=[
                _normalize_rel_path(str(item)) or ""
                for item in payload.get("illustrations", [])
                if str(item).strip()
            ],
            runtime_config=dict(payload.get("runtime_config") or {}),
            memory_init_state=dict(payload.get("memory_init_state") or {}),
            created_at=str(payload.get("created_at") or _now_iso()),
            updated_at=str(payload.get("updated_at") or _now_iso()),
        )


class RoleStore:
    def __init__(self, workspace: Path) -> None:
        self.workspace = workspace
        self.roles_dir = workspace / "roles"
        self.assets_dir = self.roles_dir / "assets"
        self.manifest_path = self.roles_dir / "roles.json"
        self._lock = threading.RLock()
        self._ensure_layout()

    def _ensure_layout(self) -> None:
        self.roles_dir.mkdir(parents=True, exist_ok=True)
        self.assets_dir.mkdir(parents=True, exist_ok=True)
        if not self.manifest_path.exists():
            self._save_roles([])

    def _load_payload(self) -> dict[str, Any]:
        payload = load_json(
            self.manifest_path,
            default={"version": _MANIFEST_VERSION, "roles": []},
            domain="roles",
        )
        if not isinstance(payload, dict):
            return {"version": _MANIFEST_VERSION, "roles": []}
        roles = payload.get("roles")
        if not isinstance(roles, list):
            roles = []
        return {
            "version": int(payload.get("version") or _MANIFEST_VERSION),
            "roles": roles,
        }

    def _save_roles(self, roles: list[RoleRecord]) -> None:
        atomic_save_json(
            self.manifest_path,
            {
                "version": _MANIFEST_VERSION,
                "roles": [role.to_dict() for role in roles],
            },
            domain="roles",
        )

    def _remove_asset_relpath(self, rel_path: str | None) -> None:
        normalized = _normalize_rel_path(rel_path)
        if not normalized:
            return
        target = self.roles_dir / normalized
        try:
            if target.is_file():
                target.unlink()
        except FileNotFoundError:
            return

    def list_roles(self) -> list[RoleRecord]:
        with self._lock:
            payload = self._load_payload()
            roles = [RoleRecord.from_dict(item) for item in payload["roles"]]
        return sorted(roles, key=lambda item: (item.updated_at, item.id), reverse=True)

    def get_role(self, role_id: str) -> RoleRecord | None:
        role_id = str(role_id).strip()
        if not role_id:
            return None
        for role in self.list_roles():
            if role.id == role_id:
                return role
        return None

    def create_role(
        self,
        *,
        name: str,
        system_prompt: str,
        description: str = "",
        background: str = "",
        runtime_config: dict[str, Any] | None = None,
        role_id: str | None = None,
        avatar_source: str | Path | None = None,
        illustration_sources: list[str | Path] | None = None,
    ) -> RoleRecord:
        clean_name = str(name).strip()
        clean_prompt = str(system_prompt).strip()
        if not clean_name:
            raise ValueError("role.name 不能为空")
        if not clean_prompt:
            raise ValueError("role.system_prompt 不能为空")

        with self._lock:
            roles = self.list_roles()
            resolved_id = str(role_id).strip() if role_id else f"role-{uuid.uuid4().hex[:12]}"
            if any(role.id == resolved_id for role in roles):
                raise ValueError(f"role 已存在: {resolved_id}")
            now = _now_iso()
            record = RoleRecord(
                id=resolved_id,
                name=clean_name,
                description=str(description),
                system_prompt=clean_prompt,
                background=str(background),
                avatar=None,
                illustrations=[],
                runtime_config=dict(runtime_config or {}),
                memory_init_state={},
                created_at=now,
                updated_at=now,
            )
            if avatar_source is not None:
                record.avatar = self.import_asset(
                    resolved_id,
                    avatar_source,
                    prefix="avatar",
                )
            if illustration_sources:
                record.illustrations = [
                    self.import_asset(resolved_id, source, prefix="illustration")
                    for source in illustration_sources
                ]
            roles.append(record)
            self._save_roles(roles)
            return record

    def update_role(
        self,
        role_id: str,
        *,
        name: str | None = None,
        description: str | None = None,
        system_prompt: str | None = None,
        background: str | None = None,
        runtime_config: dict[str, Any] | None = None,
        memory_init_state: dict[str, Any] | None = None,
        avatar_source: str | Path | None = None,
        clear_avatar: bool = False,
        illustration_sources: list[str | Path] | None = None,
        clear_illustrations: bool = False,
    ) -> RoleRecord:
        with self._lock:
            roles = self.list_roles()
            for index, role in enumerate(roles):
                if role.id != role_id:
                    continue
                if name is not None:
                    clean_name = str(name).strip()
                    if not clean_name:
                        raise ValueError("role.name 不能为空")
                    role.name = clean_name
                if description is not None:
                    role.description = str(description)
                if system_prompt is not None:
                    clean_prompt = str(system_prompt).strip()
                    if not clean_prompt:
                        raise ValueError("role.system_prompt 不能为空")
                    role.system_prompt = clean_prompt
                if background is not None:
                    role.background = str(background)
                if runtime_config is not None:
                    role.runtime_config = dict(runtime_config)
                if memory_init_state is not None:
                    role.memory_init_state = dict(memory_init_state)
                if clear_avatar:
                    self._remove_asset_relpath(role.avatar)
                    role.avatar = None
                if avatar_source is not None:
                    self._remove_asset_relpath(role.avatar)
                    role.avatar = self.import_asset(role.id, avatar_source, prefix="avatar")
                if clear_illustrations:
                    for rel_path in role.illustrations:
                        self._remove_asset_relpath(rel_path)
                    role.illustrations = []
                if illustration_sources:
                    role.illustrations.extend(
                        self.import_asset(role.id, source, prefix="illustration")
                        for source in illustration_sources
                    )
                role.updated_at = _now_iso()
                roles[index] = role
                self._save_roles(roles)
                return role
        raise KeyError(f"role 不存在: {role_id}")

    def delete_role(self, role_id: str, *, remove_assets: bool = True) -> bool:
        with self._lock:
            roles = self.list_roles()
            kept = [role for role in roles if role.id != role_id]
            if len(kept) == len(roles):
                return False
            self._save_roles(kept)
            if remove_assets:
                asset_dir = self.assets_dir / role_id
                if asset_dir.exists():
                    shutil.rmtree(asset_dir, ignore_errors=True)
            return True

    def import_asset(
        self,
        role_id: str,
        source: str | Path,
        *,
        prefix: str,
    ) -> str:
        src = Path(source).expanduser()
        if not src.is_file():
            raise FileNotFoundError(f"角色素材不存在: {src}")
        role_assets_dir = self.assets_dir / role_id
        role_assets_dir.mkdir(parents=True, exist_ok=True)
        suffix = src.suffix or ""
        target_name = f"{prefix}-{uuid.uuid4().hex[:8]}{suffix}"
        target = role_assets_dir / target_name
        shutil.copy2(src, target)
        return target.relative_to(self.roles_dir).as_posix()
