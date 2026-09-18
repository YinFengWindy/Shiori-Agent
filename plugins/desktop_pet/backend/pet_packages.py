"""Plugin-owned Codex sprite package validation and import."""

from __future__ import annotations

import os
import shutil
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

from core.roles.store import RoleStore

from .models import RolePetPackage, RolePetState
from .pet_state import RolePetStateStore
from .storage import prepare_assets, role_asset_directory
from . import package_archive, package_images
from core.roles.models import now_iso

_FORMAT = "codex-sprite@1"


class RolePetPackageService:
    """Handles only complete, self-contained pet packages under the plugin’s private asset root."""

    def __init__(self, role_store: RoleStore) -> None:
        self._role_store = role_store
        prepare_assets(role_store)
        self._state = RolePetStateStore(role_store)

    def import_package(self, role_id: str, source: str | Path) -> RolePetPackage:
        """Validates a ZIP first, then atomically promotes it into the plugin’s role-specific directory."""
        with self._role_store.lock:
            prepare_assets(self._role_store)
            return self._import_package(role_id, source)

    def _import_package(self, role_id: str, source: str | Path) -> RolePetPackage:
        source_path = Path(source).expanduser()
        if not source_path.is_file():
            raise FileNotFoundError(f"桌宠包不存在: {source_path}")
        role = self._state.get_role(role_id)
        if role is None:
            raise KeyError(f"role 不存在: {role_id}")
        with zipfile.ZipFile(source_path) as archive:
            names, root = package_archive.archive_names(archive)
            manifest = package_archive.manifest(archive, root)
            actions = package_archive.manifest_actions(manifest)
            package_id = str(manifest["id"]).strip()
            if (
                "\\" in package_id
                or ":" in package_id
                or PurePosixPath(package_id).name != package_id
                or package_id
                in {
                    ".",
                    "..",
                }
            ):
                raise ValueError("桌宠包 id 不安全")
            sprite_name = package_archive.safe_relative_path(
                str(manifest["spritesheetPath"])
            )
            raw_preview_name = manifest.get("previewPath")
            if raw_preview_name is None:
                preview_name = None
            elif not isinstance(raw_preview_name, str) or not raw_preview_name.strip():
                raise ValueError("桌宠包 previewPath 无效")
            else:
                preview_name = package_archive.safe_relative_path(raw_preview_name)
            if sprite_name not in names:
                raise ValueError("桌宠包缺少 spritesheet")
            if preview_name is not None and preview_name not in names:
                raise ValueError("桌宠包缺少预览图")
            if any(item.id == package_id for item in role.pet_packages):
                raise ValueError(f"桌宠包已存在: {package_id}")
            package_images.validate_atlas(
                archive.read(package_archive.archive_entry(root, sprite_name))
            )
            preview_data = None
            preview_extension = None
            if preview_name is not None:
                preview_data = archive.read(
                    package_archive.archive_entry(root, preview_name)
                )
                preview_extension = package_images.validate_preview(preview_data)
            destination = self._package_directory(role_id, package_id)
            if destination.exists():
                raise ValueError(f"桌宠包目录已存在: {package_id}")
            destination.parent.mkdir(parents=True, exist_ok=True)
            temporary = Path(
                tempfile.mkdtemp(prefix=f".{package_id}-", dir=destination.parent)
            )
            try:
                (temporary / "pet.json").write_bytes(
                    archive.read(package_archive.archive_entry(root, "pet.json"))
                )
                (temporary / "spritesheet.webp").write_bytes(
                    archive.read(package_archive.archive_entry(root, sprite_name))
                )
                preview_filename = None
                if preview_data is not None and preview_extension is not None:
                    preview_filename = f"preview{preview_extension}"
                    (temporary / preview_filename).write_bytes(preview_data)
                os.replace(temporary, destination)
            except Exception:
                shutil.rmtree(temporary, ignore_errors=True)
                raise
        root = destination.relative_to(self._role_store.workspace.resolve()).as_posix()
        package = RolePetPackage(
            id=package_id,
            format=_FORMAT,
            display_name=str(manifest["displayName"]).strip(),
            manifest_path=f"{root}/pet.json",
            spritesheet_path=f"{root}/spritesheet.webp",
            imported_at=now_iso(),
            preview_path=f"{root}/{preview_filename}" if preview_filename else None,
            actions=actions,
        )
        try:
            self._state.replace_packages(role_id, [*role.pet_packages, package])
        except Exception:
            shutil.rmtree(destination, ignore_errors=True)
            raise
        return package

    def remove_package(self, role_id: str, package_id: str) -> None:
        """Removes all package files and its metadata as one role-owned asset operation."""
        with self._role_store.lock:
            self._remove_package(role_id, package_id)

    def _remove_package(self, role_id: str, package_id: str) -> None:
        role = self._state.require_role(role_id)
        package = next(
            (item for item in role.pet_packages if item.id == package_id), None
        )
        if package is None:
            raise KeyError(f"桌宠包不存在: {package_id}")
        self._state.replace_packages(
            role_id, [item for item in role.pet_packages if item.id != package_id]
        )
        destination = self._package_directory(role_id, package_id)
        if destination.exists():
            shutil.rmtree(destination)

    def select_package(self, role_id: str, package_id: str) -> RolePetState:
        """Selects one installed package without changing desktop-pet visibility."""
        return self._state.select_package(role_id, package_id)

    def _package_directory(self, role_id: str, package_id: str) -> Path:
        for identifier in (role_id, package_id):
            if (
                not identifier
                or any(char in identifier for char in ("/", "\\", ":"))
                or identifier in {".", ".."}
            ):
                raise ValueError("桌宠包所属路径不安全")
        root = role_asset_directory(self._role_store.workspace, role_id).resolve()
        destination = (root / package_id).resolve()
        destination.relative_to(root)
        return destination
