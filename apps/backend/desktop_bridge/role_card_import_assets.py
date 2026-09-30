"""Asset validation, staging, and role metadata for confirmed card imports."""

from __future__ import annotations

import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from core.common.media import write_png_thumbnail
from core.roles import RoleAggregateService, RoleAssetCategory
from core.roles.card_import.models import RoleCardAsset


def write_asset_preview(data: bytes, target: Path) -> bool:
    """Decode a bounded thumbnail; propagate errors writing it to disk."""
    try:
        write_png_thumbnail(data, target, 320)
    except ValueError:
        return False
    return True


def resolve_emotion_selections(
    assets: tuple[RoleCardAsset, ...], raw: Any
) -> dict[str, str]:
    """Require explicit valid selections for each duplicate named emotion."""
    groups: dict[str, list[str]] = {}
    for asset in assets:
        if asset.kind == "emotion" and asset.name and asset.data is not None:
            groups.setdefault(asset.name, []).append(asset.asset_id)
    if raw is not None and not isinstance(raw, dict):
        raise ValueError("心情素材选择无效")
    selections = raw or {}
    if any(
        name not in groups or asset_id not in groups[name]
        for name, asset_id in selections.items()
    ):
        raise ValueError("心情素材选择无效")
    resolved: dict[str, str] = {}
    for name, candidates in groups.items():
        if len(candidates) > 1 and name not in selections:
            raise ValueError(f"请选择心情 {name} 对应的素材")
        resolved[name] = selections.get(name, candidates[0])
    return resolved


@contextmanager
def stage_assets(assets: tuple[RoleCardAsset, ...], staging_root: Path):
    """Stage validated bytes and always remove partially written temporary files."""
    staged: list[tuple[RoleCardAsset, Path]] = []
    try:
        for asset in assets:
            if asset.data is None:
                continue
            extensions = {
                "image/png": ".png",
                "image/jpeg": ".jpg",
                "image/webp": ".webp",
                "image/gif": ".gif",
            }
            if asset.media_type is None or asset.media_type not in extensions:
                raise ValueError("角色卡素材格式无效")
            extension = extensions[asset.media_type]
            with tempfile.NamedTemporaryFile(
                prefix="shiori-role-card-",
                suffix=extension,
                dir=staging_root,
                delete=False,
            ) as handle:
                staged.append((asset, Path(handle.name)))
                handle.write(asset.data)
        yield staged
    finally:
        for _asset, temporary_path in staged:
            temporary_path.unlink(missing_ok=True)


async def apply_asset_metadata(
    service: RoleAggregateService,
    role_id: str,
    illustration_paths: list[str],
    staged: list[tuple[RoleCardAsset, Path]],
    selections: dict[str, str],
):
    """Bind selected moods and the declared background to imported role assets."""
    category = RoleAssetCategory(
        id="imported-role-card", name="导入角色卡", allow_role_send=False
    )
    bindings = {path: category.id for path in illustration_paths}
    background_path = next(
        (
            path
            for path, (asset, _) in zip(illustration_paths, staged)
            if asset.kind == "background"
        ),
        None,
    )
    mood_bindings = {
        asset.name: path
        for path, (asset, _) in zip(illustration_paths, staged)
        if asset.kind == "emotion"
        and asset.name
        and selections.get(asset.name) == asset.asset_id
    }
    current = service.repository.get_required(role_id)
    runtime_config = dict(current.runtime_config)
    if mood_bindings:
        runtime_config["mood_illustration_bindings"] = mood_bindings
        runtime_config["mood_catalog"] = list(mood_bindings)
        if "neutral" in mood_bindings:
            runtime_config["default_mood"] = "neutral"
    return await service.update_role_async(
        role_id,
        runtime_config=runtime_config,
        chat_background=background_path,
        asset_categories=[*current.asset_categories, category],
        asset_category_bindings=bindings,
    )
