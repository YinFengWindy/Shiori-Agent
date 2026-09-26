from __future__ import annotations

import shutil
import uuid
from pathlib import Path
from typing import Any

from core.roles import RoleAggregateService, RoleStore
from core.roles.card_import import RoleCardImportService
from .role_card_import_assets import (
    apply_asset_metadata,
    resolve_emotion_selections,
    stage_assets,
    write_asset_preview,
)


class DesktopRoleCardImportService:
    """Owns the desktop role-card staging, preview, and commit workflow."""

    def __init__(
        self,
        *,
        workspace: Path,
        role_service: RoleAggregateService,
        role_store: RoleStore,
    ) -> None:
        self._workspace = workspace.resolve()
        self._role_service = role_service
        self._role_store = role_store
        self._parser = RoleCardImportService()
        self._staging_root = (
            self._workspace / "private_runtime" / "imports" / "role-cards"
        ).resolve()
        self._staging_root.mkdir(parents=True, exist_ok=True)
        self._imports: dict[str, Path] = {}
        self._committing: set[str] = set()
        self._pending_roles: dict[str, str] = {}
        for child in self._staging_root.iterdir():
            # Only preview-thumbnail directories live under the staging root;
            # staged card files are plain files and must survive restarts.
            if child.is_dir():
                shutil.rmtree(child, ignore_errors=True)

    async def preview(self, payload: dict[str, Any]) -> dict[str, Any]:
        source = self._validate_source(payload.get("source"))
        preview = self._parser.preview(source)
        import_id = uuid.uuid4().hex
        result = preview.to_dict()
        preview_dir = self._staging_root / import_id
        try:
            for index, (asset, asset_payload) in enumerate(
                zip(preview.assets, result["assets"])
            ):
                if asset.data is None:
                    continue
                preview_dir.mkdir(parents=True, exist_ok=True)
                target = preview_dir / f"asset-{index}.png"
                if write_asset_preview(asset.data, target):
                    asset_payload["preview_abs"] = str(target)
        except Exception:
            self._cleanup_preview_assets(import_id)
            raise
        self._imports[import_id] = source
        result.update(
            {
                "import_id": import_id,
                "system_prompt": str(
                    preview.profile.get("character", {}).get("behavior_rules") or ""
                ),
            }
        )
        return result

    async def commit(self, payload: dict[str, Any]) -> dict[str, Any]:
        import_id = str(payload.get("import_id") or "").strip()
        if import_id in self._committing:
            raise ValueError("角色卡正在提交，请等待完成")
        source = self._imports.get(import_id)
        if source is None:
            raise ValueError("角色卡导入预览已失效，请重新选择文件")
        preview = self._parser.preview(source)
        overrides = payload.get("overrides")
        overrides = overrides if isinstance(overrides, dict) else {}
        name = str(overrides.get("name") or preview.name).strip()
        description = str(overrides.get("description", preview.description))
        selections = resolve_emotion_selections(
            preview.assets, payload.get("emotion_selections")
        )
        profile = self._profile_with_overrides(preview, overrides.get("profile"))
        character = dict(profile.get("character") or {})
        requested_prompt = str(overrides.get("system_prompt") or "").strip()
        if requested_prompt:
            character["behavior_rules"] = requested_prompt
        profile["character"] = character
        system_prompt = str(character.get("behavior_rules") or "").strip()
        if not system_prompt:
            system_prompt = "请遵循角色资料进行自然对话。"

        self._rollback_pending_role(import_id)
        self._committing.add(import_id)
        try:
            with stage_assets(preview.assets, self._staging_root) as staged:
                role_id = f"role-{uuid.uuid4().hex[:12]}"
                self._pending_roles[import_id] = role_id
                aggregate = await self._role_service.create_role_async(
                    role_id=role_id,
                    name=name,
                    description=description,
                    system_prompt=system_prompt,
                    profile=profile,
                    # An explicit empty override removes the card's default avatar.
                    avatar_source=(
                        str(overrides["avatar_source"]).strip() or None
                        if "avatar_source" in overrides
                        else next(
                            (path for asset, path in staged if asset.kind == "avatar"),
                            None,
                        )
                    ),
                    illustration_sources=[path for _, path in staged],
                )
                if staged:
                    aggregate = await apply_asset_metadata(
                        self._role_service,
                        aggregate.role.id,
                        aggregate.role.illustrations,
                        staged,
                        selections,
                    )
            self._pending_roles.pop(import_id, None)
            self._imports.pop(import_id, None)
            self._cleanup_preview_assets(import_id)
            return {"role": aggregate.role.to_dict()}
        except BaseException:
            # Creation can persist the record before awaiting memory initialization.
            # Keep failed rollback IDs so retries cannot silently create duplicates.
            self._rollback_pending_role(import_id)
            raise
        finally:
            self._committing.discard(import_id)

    def _rollback_pending_role(self, import_id: str) -> None:
        role_id = self._pending_roles.get(import_id)
        if role_id is None:
            return
        if self._role_store.get_role(role_id) is not None:
            self._role_service.delete_role(role_id)
        self._pending_roles.pop(import_id, None)

    async def cancel(self, payload: dict[str, Any]) -> dict[str, Any]:
        import_id = str(payload.get("import_id") or "").strip()
        if import_id in self._committing:
            raise ValueError("角色卡正在提交，请等待完成")
        self._rollback_pending_role(import_id)
        self._imports.pop(import_id, None)
        self._cleanup_preview_assets(import_id)
        return {"cancelled": bool(import_id)}

    def _cleanup_preview_assets(self, import_id: str) -> None:
        if not import_id:
            return
        preview_dir = (self._staging_root / import_id).resolve()
        if preview_dir.parent == self._staging_root and preview_dir.is_dir():
            shutil.rmtree(preview_dir, ignore_errors=True)

    def _validate_source(self, raw_source: Any) -> Path:
        source = Path(str(raw_source or "")).expanduser().resolve()
        try:
            source.relative_to(self._staging_root)
        except ValueError as error:
            raise ValueError("角色卡文件必须来自受控导入目录") from error
        if not source.is_file():
            raise FileNotFoundError(f"角色卡不存在: {source.name}")
        if source.suffix.casefold() not in {".json", ".png", ".apng", ".charx"}:
            raise ValueError("不支持的角色卡格式")
        return source

    @staticmethod
    def _profile_with_overrides(preview: Any, raw_overrides: Any) -> dict[str, Any]:
        profile = dict(preview.profile)
        if preview.provenance is not None:
            profile["import_provenance"] = preview.provenance.to_dict()
        overrides = raw_overrides if isinstance(raw_overrides, dict) else {}
        for section in ("character",):
            value = overrides.get(section)
            if isinstance(value, dict):
                profile[section] = {**dict(profile.get(section) or {}), **value}
        return profile
