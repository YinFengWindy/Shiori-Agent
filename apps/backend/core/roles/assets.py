from __future__ import annotations

import shutil
import uuid
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from .models import RoleAssetCategory, RoleRecord, normalize_rel_path


class RoleAssetStore:
    """Owns role asset paths, files, and category validation."""

    def __init__(self, roles_dir: Path, assets_dir: Path) -> None:
        self.roles_dir = roles_dir
        self.assets_dir = assets_dir

    def import_asset(self, role_id: str, source: str | Path, *, prefix: str) -> str:
        src = Path(source).expanduser()
        if not src.is_file():
            raise FileNotFoundError(f"角色素材不存在: {src}")
        role_assets_dir = self.assets_dir / role_id
        role_assets_dir.mkdir(parents=True, exist_ok=True)
        target = role_assets_dir / f"{prefix}-{uuid.uuid4().hex[:8]}{src.suffix or ''}"
        shutil.copy2(src, target)
        return target.relative_to(self.roles_dir).as_posix()

    def remove(self, rel_path: str | None) -> None:
        target = self.resolve_path(rel_path)
        if target is None:
            return
        try:
            if target.is_file():
                target.unlink()
        except FileNotFoundError:
            return

    def delete_role_data(self, role_id: str, *, remove_assets: bool) -> None:
        if remove_assets:
            asset_dir = self.assets_dir / role_id
            if asset_dir.exists():
                shutil.rmtree(asset_dir, ignore_errors=True)
        role_runtime_dir = self.roles_dir / role_id
        if role_runtime_dir.exists():
            shutil.rmtree(role_runtime_dir)

    def resolve_path(self, rel_path: str | None) -> Path | None:
        normalized = normalize_rel_path(rel_path)
        if not normalized:
            return None
        target = (self.roles_dir / normalized).resolve()
        try:
            target.relative_to(self.assets_dir.resolve())
        except ValueError:
            raise ValueError(f"角色素材路径越界: {normalized}") from None
        return target

    def is_role_asset_path(self, role_id: str, rel_path: str) -> bool:
        normalized = normalize_rel_path(rel_path)
        if not normalized:
            return False
        target = (self.roles_dir / normalized).resolve()
        role_assets_dir = (self.assets_dir / role_id).resolve()
        try:
            target.relative_to(role_assets_dir)
        except ValueError:
            return False
        return target.is_file()

    @staticmethod
    def normalize_categories(
        categories: Sequence[RoleAssetCategory | dict[str, Any]],
    ) -> list[RoleAssetCategory]:
        normalized = [
            (
                item
                if isinstance(item, RoleAssetCategory)
                else RoleAssetCategory.from_dict(item)
            )
            for item in categories
        ]
        if not normalized:
            raise ValueError("角色素材库至少需要一个分类")
        ids = [category.id for category in normalized]
        names = [category.name.casefold() for category in normalized]
        if len(ids) != len(set(ids)):
            raise ValueError("角色素材分类 id 不能重复")
        if len(names) != len(set(names)):
            raise ValueError("角色素材分类名称不能重复")
        return normalized

    @staticmethod
    def normalize_category_bindings(
        role: RoleRecord,
        bindings: dict[str, str],
        *,
        categories: list[RoleAssetCategory] | None = None,
    ) -> dict[str, str]:
        available_categories = categories or role.asset_categories
        category_ids = {category.id for category in available_categories}
        illustration_paths = set(role.illustrations)
        normalized: dict[str, str] = {}
        for raw_path, raw_category_id in bindings.items():
            path = normalize_rel_path(str(raw_path)) or ""
            category_id = str(raw_category_id).strip()
            if path not in illustration_paths:
                raise ValueError(f"角色素材不存在: {path}")
            if category_id not in category_ids:
                raise ValueError(f"角色素材分类不存在: {category_id}")
            normalized[path] = category_id
        default_category_id = available_categories[0].id
        for path in role.illustrations:
            normalized.setdefault(path, default_category_id)
        return normalized
