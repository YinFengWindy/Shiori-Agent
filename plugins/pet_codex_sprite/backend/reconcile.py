"""Retryable migration and cleanup owned by the sprite provider."""

from dataclasses import replace
import hashlib
import os
from pathlib import Path
import shutil
from typing import Any
from uuid import uuid4
from shiori_sdk.roles import Roles
from shiori_sdk.role_events import RoleDeleted
from shiori_sdk.storage import plugin_data_dir
from plugins.desktop_pet.backend.api import PetProvidersAPI
from .models import RolePetPackage
from .pet_state import RolePetStateStore
from .provider import SPRITE_PROVIDER
from .storage import PLUGIN_ID, role_asset_directory, safe_role_id
from .package_archive import manifest_actions


class SpriteReconciler:
    """Copy, publish, adopt, then retire source files; retry every interrupted step."""

    def __init__(self, roles: Roles, workspace: Path, desktop: PetProvidersAPI) -> None:
        self.roles, self.workspace, self.desktop = roles, workspace.resolve(), desktop
        self.state = RolePetStateStore(roles)

    def reconcile(self) -> None:
        """Migrate first, so abandoned-copy cleanup cannot erase a pending migration."""
        with self.roles.read_scope():
            role_ids = {role.id for role in self.roles.list_roles()}
            for role_id in role_ids:
                legacy = self.desktop.legacy_state(role_id)
                if legacy is not None:
                    self._migrate(role_id, legacy)
                self._cleanup_legacy(role_id)

            def prune(data):
                for role_id in list(data):
                    if role_id not in role_ids:
                        del data[role_id]

            self.roles.extensions.update(PLUGIN_ID, prune)
            root = plugin_data_dir(self.workspace, PLUGIN_ID)
            if root.exists():
                for directory in root.glob("pets-*"):
                    if directory.is_symlink():
                        raise ValueError("桌宠素材目录不能是符号链接")
                    if not directory.is_dir():
                        continue
                    role_id = directory.name.removeprefix("pets-")
                    if role_id not in role_ids:
                        shutil.rmtree(directory)
                        continue
                    installed = {
                        p.id for p in self.state.require_role(role_id).pet_packages
                    }
                    for child in directory.iterdir():
                        if (
                            child.is_dir()
                            and not child.is_symlink()
                            and child.name not in installed
                        ):
                            shutil.rmtree(child)

    def _migrate(self, role_id: str, legacy: dict[str, Any]) -> None:
        packages = [
            RolePetPackage.from_dict(
                {**p, "imported_at": p.get("imported_at") or "legacy"}
            )
            for p in legacy.get("pet_packages", [])
        ]
        current = self.state.require_role(role_id).pet_packages
        merged = {p.id: p for p in current}
        cleanup: list[str] = []
        for package in packages:
            safe_role_id(package.id)
            manifest_actions({"actions": package.actions})
            paths: dict[str, str | None] = {}
            source_dirs: set[Path] = set()
            for field in ("manifest_path", "spritesheet_path", "preview_path"):
                relative = getattr(package, field)
                if relative is None:
                    paths[field] = None
                    continue
                source = self._legacy_path(role_id, relative)
                target = (
                    role_asset_directory(self.workspace, role_id)
                    / package.id
                    / source.name
                )
                self._copy(source, target)
                paths[field] = target.relative_to(self.workspace).as_posix()
                source_dirs.add(source.parent)
            migrated = replace(package, **paths)
            existing = merged.get(package.id)
            if existing is not None and existing != migrated:
                raise ValueError(f"迁移桌宠包与现有包冲突: {package.id}")
            merged[package.id] = migrated
            cleanup.extend(
                p.relative_to(self.workspace).as_posix() for p in source_dirs
            )

        def publish(data):
            previous = data.get(role_id, {})
            data[role_id] = {
                **previous,
                "packages": [p.to_dict() for p in merged.values()],
                "legacy_cleanup": sorted(
                    set(previous.get("legacy_cleanup", []) + cleanup)
                ),
            }

        self.roles.extensions.update(PLUGIN_ID, publish)
        selected = legacy.get("selected_pet_package_id")
        self.desktop.adopt_legacy(
            role_id, selected if selected in merged else None, SPRITE_PROVIDER
        )

    def _legacy_path(self, role_id: str, relative: str) -> Path:
        source = self.workspace / relative
        roots = [
            self.workspace
            / "plugin-data"
            / "desktop_pet"
            / f"pets-{safe_role_id(role_id)}",
            self.roles.asset_path(f"assets/{safe_role_id(role_id)}/pets"),
        ]
        canonical = source.resolve()
        if source.resolve() != source or any(root.resolve() != root for root in roots):
            raise ValueError("旧桌宠素材路径包含链接或越界")
        if not any(
            canonical.is_relative_to(root.resolve()) and canonical != root.resolve()
            for root in roots
        ):
            raise ValueError("旧桌宠素材路径越界")
        if source.is_symlink() or not source.is_file():
            raise FileNotFoundError(f"旧桌宠素材不可用: {relative}")
        return source

    @staticmethod
    def _copy(source: Path, target: Path) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.is_symlink() or target.parent.resolve() != target.parent:
            raise ValueError("桌宠迁移目标路径越界")
        if target.exists():
            if (
                hashlib.sha256(target.read_bytes()).digest()
                != hashlib.sha256(source.read_bytes()).digest()
            ):
                raise ValueError(f"桌宠迁移目标内容冲突: {target.name}")
            return
        temporary = target.with_name(f".{target.name}-{uuid4().hex}.tmp")
        try:
            shutil.copyfile(source, temporary)
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)

    def _cleanup_legacy(self, role_id: str) -> None:
        raw: Any = self.roles.extensions.read(PLUGIN_ID).get(role_id, {})
        cleanup = raw.get("legacy_cleanup", [])
        if not cleanup or self.desktop.legacy_state(role_id) is not None:
            return
        for relative in cleanup:
            directory = self.workspace / relative
            root = (
                self.workspace
                / "plugin-data"
                / "desktop_pet"
                / f"pets-{safe_role_id(role_id)}"
            )
            old_root = self.roles.asset_path(
                f"assets/{safe_role_id(role_id)}/pets"
            ).resolve()
            if directory.resolve() != directory or not any(
                directory.resolve().is_relative_to(p.resolve())
                and directory.resolve() != p.resolve()
                for p in (root, old_root)
            ):
                raise ValueError("旧桌宠清理目录越界")
            if directory.is_dir():
                shutil.rmtree(directory)

        def finish(data):
            data[role_id] = {
                key: value
                for key, value in data[role_id].items()
                if key != "legacy_cleanup"
            }

        self.roles.extensions.update(PLUGIN_ID, finish)

    async def on_role_deleted(self, _event: RoleDeleted) -> None:
        """Reconcile role-owned resources after deletion."""
        self.reconcile()
