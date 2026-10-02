"""Validation and preparation of model selections accompanying a settings commit."""

from __future__ import annotations

from typing import Any

from shiori_sdk.values import now_iso
from .store import RoleStore

_BINDING_KEYS = ("dialogue_model_registration_id", "visual_model_registration_id")
_EFFORT_KEYS = ("dialogue_model_effort", "visual_model_effort")


def prepare_role_model_updates(
    store: RoleStore,
    updates: list[dict[str, Any]],
    registration_ids: set[str],
) -> dict[str, Any] | None:
    """Merges only model fields into current roles; never replaces unrelated state."""
    if not updates:
        return None
    payload = store._repository.load_payload()
    roles = {item["id"]: item for item in payload["roles"]}
    seen: set[str] = set()
    for update in updates:
        role_id = update.get("role_id")
        if not isinstance(role_id, str) or role_id not in roles:
            raise ValueError(f"角色不存在: {role_id}")
        if role_id in seen:
            raise ValueError(f"角色模型更新重复: {role_id}")
        seen.add(role_id)
        selection = update.get("runtime_config")
        if not isinstance(selection, dict):
            raise ValueError("角色模型更新必须包含 runtime_config")
        role = roles[role_id]
        config = dict(role.get("runtime_config") or {})
        for key in _BINDING_KEYS:
            if key not in selection:
                continue
            value = selection[key]
            if not isinstance(value, str):
                raise ValueError(f"{key} 必须是字符串")
            if value and value not in registration_ids:
                raise ValueError(f"角色引用了不存在的模型注册: {value}")
            config[key] = value
        for key in _EFFORT_KEYS:
            if key in selection:
                if selection[key] not in {"", "none", "low", "high", "max"}:
                    raise ValueError(f"{key} 无效")
                config[key] = selection[key]
        if config != role.get("runtime_config"):
            role["runtime_config"] = config
            role["updated_at"] = now_iso()
    return payload
