from __future__ import annotations

from typing import Any

CURRENT_MANIFEST_VERSION = 9


def migrate_manifest_payload(payload: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """Read a released 0.5.x role manifest. Current files are version 9."""

    version = int(payload.get("version") or 0)
    roles = payload.get("roles")
    if not isinstance(roles, list):
        raise ValueError("角色清单格式无效：roles 必须是数组")
    for item in roles:
        if not isinstance(item, dict):
            raise ValueError("角色清单格式无效：角色记录必须是对象")
        if not isinstance(item.get("profile"), dict):
            raise ValueError("角色清单格式无效：profile 必须是对象")

    if version == CURRENT_MANIFEST_VERSION:
        return dict(payload), False
    # 3 and 5 shipped before 0.5.0 and were still readable in every 0.5.x
    # release. 2/4/6/7/8 never shipped. v10 was never released.
    if version not in {3, 5, 9}:
        raise ValueError(
            f"角色清单版本不支持：需要版本 {CURRENT_MANIFEST_VERSION}，实际为 {version}"
        )

    migrated_roles = [dict(item) for item in roles]
    return {
        **payload,
        "version": CURRENT_MANIFEST_VERSION,
        "roles": migrated_roles,
    }, True
