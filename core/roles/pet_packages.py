"""Role-owned Codex sprite package validation and import."""

from __future__ import annotations

import io
import json
import os
import shutil
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path, PurePosixPath

from PIL import Image

from .store import RolePetPackage, RoleRecord, RoleStore

_FORMAT = "codex-sprite@1"
_ATLAS_SIZE = (1536, 1872)
_CELL_SIZE = (192, 208)
_USED_CELLS = (6, 8, 8, 4, 5, 8, 6, 6, 6)


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat()


def _safe_relative_path(value: str) -> str:
    path = PurePosixPath(value)
    if not value or path.is_absolute() or ".." in path.parts or path == ".":
        raise ValueError("桌宠包路径不安全")
    return path.as_posix()


class RolePetPackageService:
    """Handles only complete, self-contained pet packages under a role asset root."""

    def __init__(self, role_store: RoleStore) -> None:
        self._role_store = role_store

    def import_package(self, role_id: str, source: str | Path) -> RolePetPackage:
        """Validates a ZIP first, then atomically promotes it into the role's pets directory."""
        source_path = Path(source).expanduser()
        if not source_path.is_file():
            raise FileNotFoundError(f"桌宠包不存在: {source_path}")
        role = self._role_store.get_role(role_id)
        if role is None:
            raise KeyError(f"role 不存在: {role_id}")
        with zipfile.ZipFile(source_path) as archive:
            names, root = self._archive_names(archive)
            manifest = self._manifest(archive, root)
            package_id = str(manifest["id"]).strip()
            if PurePosixPath(package_id).name != package_id or package_id in {".", ".."}:
                raise ValueError("桌宠包 id 不安全")
            sprite_name = _safe_relative_path(str(manifest["spritesheetPath"]))
            if sprite_name not in names:
                raise ValueError("桌宠包缺少 spritesheet")
            if any(item.id == package_id for item in role.pet_packages):
                raise ValueError(f"桌宠包已存在: {package_id}")
            self._validate_atlas(archive.read(self._archive_entry(root, sprite_name)))
            destination = self._role_store.assets_dir / role_id / "pets" / package_id
            if destination.exists():
                raise ValueError(f"桌宠包目录已存在: {package_id}")
            destination.parent.mkdir(parents=True, exist_ok=True)
            temporary = Path(tempfile.mkdtemp(prefix=f".{package_id}-", dir=destination.parent))
            try:
                (temporary / "pet.json").write_bytes(archive.read(self._archive_entry(root, "pet.json")))
                (temporary / "spritesheet.webp").write_bytes(archive.read(self._archive_entry(root, sprite_name)))
                os.replace(temporary, destination)
            except Exception:
                shutil.rmtree(temporary, ignore_errors=True)
                raise
        root = destination.relative_to(self._role_store.roles_dir).as_posix()
        package = RolePetPackage(
            id=package_id,
            format=_FORMAT,
            display_name=str(manifest["displayName"]).strip(),
            manifest_path=f"{root}/pet.json",
            spritesheet_path=f"{root}/spritesheet.webp",
            imported_at=_now_iso(),
        )
        try:
            self._role_store.replace_pet_packages(role_id, [*role.pet_packages, package])
        except Exception:
            shutil.rmtree(destination, ignore_errors=True)
            raise
        return package

    def remove_package(self, role_id: str, package_id: str) -> None:
        """Removes all package files and its metadata as one role-owned asset operation."""
        role = self._role_store.get_role(role_id)
        if role is None:
            raise KeyError(f"role 不存在: {role_id}")
        package = next((item for item in role.pet_packages if item.id == package_id), None)
        if package is None:
            raise KeyError(f"桌宠包不存在: {package_id}")
        self._role_store.replace_pet_packages(role_id, [item for item in role.pet_packages if item.id != package_id])
        shutil.rmtree((self._role_store.roles_dir / package.manifest_path).resolve().parent, ignore_errors=True)

    def select_package(self, role_id: str, package_id: str) -> RoleRecord:
        """Selects one installed package without changing desktop-pet visibility."""
        return self._role_store.select_pet_package(role_id, package_id)

    def _archive_names(self, archive: zipfile.ZipFile) -> tuple[set[str], str]:
        names: set[str] = set()
        for entry in archive.infolist():
            if entry.is_dir():
                continue
            name = _safe_relative_path(entry.filename)
            if name in names:
                raise ValueError("桌宠包包含重复路径")
            names.add(name)
        if "pet.json" in names:
            return names, ""
        roots = {PurePosixPath(name).parts[0] for name in names if len(PurePosixPath(name).parts) > 1}
        if len(roots) != 1:
            raise ValueError("桌宠包缺少 pet.json")
        root = next(iter(roots))
        logical_names = {
            PurePosixPath(name).relative_to(root).as_posix()
            for name in names
            if PurePosixPath(name).parts[0] == root
        }
        if "pet.json" not in logical_names:
            raise ValueError("桌宠包缺少 pet.json")
        return logical_names, root

    def _archive_entry(self, root: str, name: str) -> str:
        return f"{root}/{name}" if root else name

    def _manifest(self, archive: zipfile.ZipFile, root: str) -> dict[str, object]:
        try:
            value = json.loads(archive.read(self._archive_entry(root, "pet.json")).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ValueError("桌宠包 pet.json 无效") from error
        if not isinstance(value, dict):
            raise ValueError("桌宠包 pet.json 必须是对象")
        for field in ("id", "displayName", "description", "spritesheetPath"):
            if not isinstance(value.get(field), str) or not str(value[field]).strip():
                raise ValueError(f"桌宠包 pet.json 缺少 {field}")
        return value

    def _validate_atlas(self, data: bytes) -> None:
        try:
            with Image.open(io.BytesIO(data)) as image:
                if image.format != "WEBP" or image.size != _ATLAS_SIZE:
                    raise ValueError("桌宠精灵图必须是 1536 x 1872 WebP")
                alpha = image.convert("RGBA").getchannel("A")
        except OSError as error:
            raise ValueError("桌宠精灵图无效") from error
        for row, count in enumerate(_USED_CELLS):
            for column in range(8):
                occupied = alpha.crop((column * _CELL_SIZE[0], row * _CELL_SIZE[1], (column + 1) * _CELL_SIZE[0], (row + 1) * _CELL_SIZE[1])).getbbox() is not None
                if column < count and not occupied:
                    raise ValueError("桌宠精灵图缺少必需动画帧")
                if column >= count and occupied:
                    raise ValueError("桌宠精灵图未使用单元必须透明")
