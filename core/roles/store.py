from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from .assets import RoleAssetStore
from .binding_policy import RoleBindingPolicy
from .manifest import RoleManifestRepository
from .models import (
    DEFAULT_ASSET_CATEGORY_ID,
    RoleAssetCategory,
    RoleChannelBindingConfig,
    RolePetPackage,
    RoleProactiveConfig,
    RoleRecord,
    default_asset_category,
    normalize_rel_path,
    now_iso,
)
from .pet_state import RolePetStateStore


class RoleStore:
    """Compatibility facade for persisted role records and owned sub-stores."""

    def __init__(
        self,
        workspace: Path,
        *,
        default_dialogue_registration_id: str = "",
    ) -> None:
        self.workspace = workspace
        self._repository = RoleManifestRepository(workspace)
        self.roles_dir = self._repository.roles_dir
        self.assets_dir = self._repository.assets_dir
        self.manifest_path = self._repository.manifest_path
        self._lock = self._repository.lock
        self._assets = RoleAssetStore(self.roles_dir, self.assets_dir)
        self._bindings = RoleBindingPolicy()
        self._pets = RolePetStateStore(self._repository)
        self._default_dialogue_registration_id = (
            default_dialogue_registration_id.strip()
        )

    def list_roles(self) -> list[RoleRecord]:
        return self._repository.list_roles()

    def get_role(self, role_id: str) -> RoleRecord | None:
        return self._repository.get_role(role_id)

    def migrate_model_selections(
        self,
        *,
        dialogue_registration_id: str,
        visual_registration_id: str = "",
    ) -> int:
        """Assigns migrated defaults only to roles without model selections."""

        changed = 0
        with self._lock:
            roles = self.list_roles()
            for role in roles:
                runtime_config = dict(role.runtime_config)
                if not str(
                    runtime_config.get("dialogue_model_registration_id") or ""
                ).strip():
                    runtime_config["dialogue_model_registration_id"] = (
                        dialogue_registration_id
                    )
                    changed += 1
                if "visual_model_registration_id" not in runtime_config:
                    runtime_config["visual_model_registration_id"] = (
                        visual_registration_id
                    )
                    changed += 1
                role.runtime_config = runtime_config
            if changed:
                self._save_roles(roles)
        return changed

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
            resolved_id = (
                str(role_id).strip() if role_id else f"role-{uuid.uuid4().hex[:12]}"
            )
            if any(role.id == resolved_id for role in roles):
                raise ValueError(f"role 已存在: {resolved_id}")
            now = now_iso()
            resolved_runtime_config = dict(runtime_config or {})
            if self._default_dialogue_registration_id:
                resolved_runtime_config.setdefault(
                    "dialogue_model_registration_id",
                    self._default_dialogue_registration_id,
                )
                resolved_runtime_config.setdefault(
                    "visual_model_registration_id",
                    "",
                )
            record = RoleRecord(
                id=resolved_id,
                name=clean_name,
                description=str(description),
                system_prompt=clean_prompt,
                background=str(background),
                avatar=None,
                chat_background=None,
                illustrations=[],
                asset_categories=[default_asset_category()],
                asset_category_bindings={},
                runtime_config=resolved_runtime_config,
                channel_bindings=[],
                proactive=RoleProactiveConfig(),
                memory_init_state={},
                created_at=now,
                updated_at=now,
                pet_packages=[],
                selected_pet_package_id=None,
                desktop_pet_enabled=False,
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
                record.asset_category_bindings = {
                    path: DEFAULT_ASSET_CATEGORY_ID for path in record.illustrations
                }
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
        channel_bindings: list[RoleChannelBindingConfig | dict[str, Any]] | None = None,
        proactive: RoleProactiveConfig | dict[str, Any] | None = None,
        memory_init_state: dict[str, Any] | None = None,
        avatar_source: str | Path | None = None,
        avatar_asset: str | None = None,
        chat_background: str | None = None,
        clear_chat_background: bool = False,
        clear_avatar: bool = False,
        illustration_sources: list[str | Path] | None = None,
        illustration_category_id: str | None = None,
        removed_illustrations: list[str] | None = None,
        clear_illustrations: bool = False,
        asset_categories: list[RoleAssetCategory | dict[str, Any]] | None = None,
        asset_category_bindings: dict[str, str] | None = None,
        desktop_pet_enabled: bool | None = None,
    ) -> RoleRecord:
        with self._lock:
            roles = self.list_roles()
            for index, role in enumerate(roles):
                if role.id != role_id:
                    continue
                self._update_fields(
                    role,
                    name=name,
                    description=description,
                    system_prompt=system_prompt,
                    background=background,
                    runtime_config=runtime_config,
                    memory_init_state=memory_init_state,
                )
                if channel_bindings is not None:
                    role.channel_bindings = self._bindings.normalize_for_role(
                        roles, role.id, channel_bindings
                    )
                    role.proactive = self._bindings.disable_missing_proactive_target(
                        role.proactive, role.channel_bindings
                    )
                if proactive is not None:
                    role.proactive = self._bindings.normalize_proactive(
                        proactive, role.channel_bindings
                    )
                self._update_asset_categories(
                    role,
                    asset_categories=asset_categories,
                    asset_category_bindings=asset_category_bindings,
                )
                if desktop_pet_enabled is not None:
                    self._pets.set_enabled(roles, role, desktop_pet_enabled)
                self._update_asset_files(
                    role,
                    avatar_source=avatar_source,
                    avatar_asset=avatar_asset,
                    chat_background=chat_background,
                    clear_chat_background=clear_chat_background,
                    clear_avatar=clear_avatar,
                    illustration_sources=illustration_sources,
                    illustration_category_id=illustration_category_id,
                    removed_illustrations=removed_illustrations,
                    clear_illustrations=clear_illustrations,
                )
                role.updated_at = now_iso()
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
            self._assets.delete_role_data(role_id, remove_assets=remove_assets)
            return True

    def import_asset(
        self,
        role_id: str,
        source: str | Path,
        *,
        prefix: str,
    ) -> str:
        """Imports one file into the role-owned asset directory."""
        return self._assets.import_asset(role_id, source, prefix=prefix)

    def resolve_role_asset_path(self, role_id: str, rel_path: str) -> Path | None:
        """Returns a validated absolute path for one asset owned by a role."""
        normalized = normalize_rel_path(rel_path)
        if not normalized or not self._assets.is_role_asset_path(role_id, normalized):
            return None
        return self._assets.resolve_path(normalized)

    def replace_pet_packages(
        self,
        role_id: str,
        packages: list[RolePetPackage],
    ) -> RoleRecord:
        """Persists the complete validated pet-package set for one role."""
        return self._pets.replace_packages(role_id, packages)

    def select_pet_package(self, role_id: str, package_id: str) -> RoleRecord:
        """Persists one role-owned pet package as that role's selected desktop pet."""
        return self._pets.select_package(role_id, package_id)

    @staticmethod
    def _update_fields(
        role: RoleRecord,
        *,
        name: str | None,
        description: str | None,
        system_prompt: str | None,
        background: str | None,
        runtime_config: dict[str, Any] | None,
        memory_init_state: dict[str, Any] | None,
    ) -> None:
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

    def _update_asset_categories(
        self,
        role: RoleRecord,
        *,
        asset_categories: list[RoleAssetCategory | dict[str, Any]] | None,
        asset_category_bindings: dict[str, str] | None,
    ) -> None:
        next_categories = (
            self._assets.normalize_categories(asset_categories)
            if asset_categories is not None
            else role.asset_categories
        )
        next_bindings = (
            self._assets.normalize_category_bindings(
                role,
                asset_category_bindings,
                categories=next_categories,
            )
            if asset_category_bindings is not None
            else role.asset_category_bindings
        )
        if asset_categories is not None and asset_category_bindings is None:
            category_ids = {category.id for category in next_categories}
            invalid_binding = next(
                (
                    category_id
                    for category_id in role.asset_category_bindings.values()
                    if category_id not in category_ids
                ),
                None,
            )
            if invalid_binding is not None:
                raise ValueError(f"素材分类仍被图片使用: {invalid_binding}")
        role.asset_categories = next_categories
        role.asset_category_bindings = next_bindings

    def _update_asset_files(
        self,
        role: RoleRecord,
        *,
        avatar_source: str | Path | None,
        avatar_asset: str | None,
        chat_background: str | None,
        clear_chat_background: bool,
        clear_avatar: bool,
        illustration_sources: list[str | Path] | None,
        illustration_category_id: str | None,
        removed_illustrations: list[str] | None,
        clear_illustrations: bool,
    ) -> None:
        if clear_avatar:
            self._assets.remove(role.avatar)
            role.avatar = None
        if avatar_source is not None:
            self._assets.remove(role.avatar)
            role.avatar = self.import_asset(role.id, avatar_source, prefix="avatar")
        if avatar_asset is not None:
            clean_avatar_asset = normalize_rel_path(avatar_asset)
            if clean_avatar_asset and not self._assets.is_role_asset_path(
                role.id, clean_avatar_asset
            ):
                raise ValueError(f"角色素材不存在: {clean_avatar_asset}")
            role.avatar = clean_avatar_asset
        if clear_chat_background:
            role.chat_background = None
        if chat_background is not None:
            clean_chat_background = normalize_rel_path(chat_background)
            if clean_chat_background and not self._assets.is_role_asset_path(
                role.id, clean_chat_background
            ):
                raise ValueError(f"角色素材不存在: {clean_chat_background}")
            role.chat_background = clean_chat_background
        if clear_illustrations:
            for rel_path in role.illustrations:
                self._assets.remove(rel_path)
            role.illustrations = []
            role.asset_category_bindings = {}
        self._remove_illustrations(role, removed_illustrations)
        if illustration_sources:
            category_id = str(illustration_category_id or "").strip()
            if not category_id:
                category_id = role.asset_categories[0].id
            if category_id not in {category.id for category in role.asset_categories}:
                raise ValueError(f"角色素材分类不存在: {category_id}")
            imported = [
                self.import_asset(role.id, source, prefix="illustration")
                for source in illustration_sources
            ]
            role.illustrations.extend(imported)
            role.asset_category_bindings.update(
                {path: category_id for path in imported}
            )

    def _remove_illustrations(
        self, role: RoleRecord, removed_illustrations: list[str] | None
    ) -> None:
        if not removed_illustrations:
            return
        removed_set = {
            normalize_rel_path(str(path)) or ""
            for path in removed_illustrations
            if str(path).strip()
        }
        if not removed_set:
            return
        kept: list[str] = []
        for rel_path in role.illustrations:
            normalized = normalize_rel_path(rel_path) or ""
            if normalized not in removed_set:
                kept.append(rel_path)
                continue
            if role.avatar == normalized:
                role.avatar = None
            if role.chat_background == normalized:
                role.chat_background = None
            self._assets.remove(normalized)
            role.asset_category_bindings.pop(normalized, None)
        role.illustrations = kept

    # Private compatibility methods remain for existing diagnostics and tests.
    def _load_payload(self) -> dict[str, Any]:
        return self._repository.load_payload()

    def _save_roles(self, roles: list[RoleRecord]) -> None:
        self._repository.save_roles(roles)

    def _resolve_asset_path(self, rel_path: str | None) -> Path | None:
        return self._assets.resolve_path(rel_path)

    def _remove_asset_relpath(self, rel_path: str | None) -> None:
        self._assets.remove(rel_path)

    def _is_role_asset_path(self, role_id: str, rel_path: str) -> bool:
        return self._assets.is_role_asset_path(role_id, rel_path)

    def _normalize_channel_bindings(
        self,
        bindings: list[RoleChannelBindingConfig | dict[str, Any]],
    ) -> list[RoleChannelBindingConfig]:
        return self._bindings.normalize(bindings)

    def _normalize_asset_categories(
        self,
        categories: list[RoleAssetCategory | dict[str, Any]],
    ) -> list[RoleAssetCategory]:
        return self._assets.normalize_categories(categories)

    def _normalize_asset_category_bindings(
        self,
        role: RoleRecord,
        bindings: dict[str, str],
        *,
        categories: list[RoleAssetCategory] | None = None,
    ) -> dict[str, str]:
        return self._assets.normalize_category_bindings(
            role, bindings, categories=categories
        )

    def _ensure_bindings_unique(
        self,
        roles: list[RoleRecord],
        role_id: str,
        bindings: list[RoleChannelBindingConfig],
    ) -> None:
        self._bindings.ensure_unique(roles, role_id, bindings)

    def _validate_desktop_bindings(
        self,
        role_id: str,
        bindings: list[RoleChannelBindingConfig],
    ) -> None:
        self._bindings.validate_desktop(role_id, bindings)
