from __future__ import annotations

from typing import Any

from .profile_models import RoleProfile

CURRENT_MANIFEST_VERSION = 5


def migrate_manifest_payload(payload: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """Normalize a legacy role manifest into v5 without dropping role-owned data."""

    version = int(payload.get("version") or 0)
    roles = payload.get("roles")
    if not isinstance(roles, list):
        raise ValueError("角色清单格式无效：roles 必须是数组")
    for item in roles:
        if not isinstance(item, dict):
            raise ValueError("角色清单格式无效：角色记录必须是对象")

    legacy_fields = ("pet_packages", "selected_pet_package_id", "desktop_pet_enabled")
    # A stale RoleRecord or older client can submit legacy fields after upgrade.
    # Normalize those writes too; runtime never reads the retired aliases.
    has_legacy_fields = any(
        any(key in role for key in legacy_fields)
        or "auto_scene_cg_enabled" in (role.get("runtime_config") or {})
        for role in roles
    )
    if version == CURRENT_MANIFEST_VERSION and not has_legacy_fields:
        return dict(payload), False
    if version not in {2, 3, 4, CURRENT_MANIFEST_VERSION}:
        raise ValueError(
            f"角色清单版本不支持：需要版本 {CURRENT_MANIFEST_VERSION}，实际为 {version}"
        )

    migrated_roles: list[dict[str, Any]] = []
    for item in roles:
        role = dict(item)
        if not isinstance(role.get("profile"), dict):
            role["profile"] = RoleProfile.from_legacy(
                system_prompt=str(role.get("system_prompt") or ""),
                background=str(role.get("background") or ""),
            ).to_dict()
        migrated_roles.append(role)
    # Upgrade-only knowledge: capture fields before RoleRecord drops them, even
    # when the plugin is disabled. One atomic manifest replacement contains both
    # the destination namespace and removal of the legacy source fields.
    plugin_data = dict(payload.get("plugin_data") or {})
    pet_data = dict(plugin_data.get("desktop_pet") or {})
    for role in migrated_roles:
        if any(key in role for key in legacy_fields):
            pet_data.setdefault(
                str(role["id"]), {key: role.get(key) for key in legacy_fields}
            )
            for key in legacy_fields:
                role.pop(key, None)
    novelai_data = dict(plugin_data.get("novelai") or {})
    for role in migrated_roles:
        runtime = dict(role.get("runtime_config") or {})
        if "auto_scene_cg_enabled" in runtime:
            novelai_data.setdefault(
                str(role["id"]),
                {"auto_scene_cg_enabled": runtime.pop("auto_scene_cg_enabled")},
            )
            role["runtime_config"] = runtime
    if novelai_data:
        plugin_data["novelai"] = novelai_data
    if pet_data:
        plugin_data["desktop_pet"] = pet_data
    return {
        **payload,
        "version": CURRENT_MANIFEST_VERSION,
        "roles": migrated_roles,
        "plugin_data": plugin_data,
    }, True
