from __future__ import annotations

import pytest

from core.roles.assets import RoleAssetStore


def test_asset_store_rejects_paths_outside_role_assets(tmp_path) -> None:
    roles_dir = tmp_path / "roles"
    assets_dir = roles_dir / "assets"
    assets_dir.mkdir(parents=True)
    store = RoleAssetStore(roles_dir, assets_dir)

    with pytest.raises(ValueError, match="路径越界"):
        store.resolve_path("../../outside.png")


def test_asset_store_rejects_duplicate_category_names(tmp_path) -> None:
    store = RoleAssetStore(tmp_path / "roles", tmp_path / "roles" / "assets")

    with pytest.raises(ValueError, match="分类名称不能重复"):
        store.normalize_categories(
            [
                {"id": "one", "name": "CG"},
                {"id": "two", "name": "cg"},
            ]
        )
