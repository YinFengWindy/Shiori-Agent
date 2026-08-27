from __future__ import annotations

from pathlib import Path

from .store import RoleRecord, RoleStore


def is_shared_memory_enabled(role: RoleRecord | None) -> bool:
    """判断角色是否显式启用了 shared 记忆域。"""

    if role is None:
        return False
    config = role.runtime_config if isinstance(role.runtime_config, dict) else {}
    if bool(config.get("shared_memory_enabled")):
        return True
    shared = config.get("shared_memory")
    if not isinstance(shared, dict):
        return False
    if bool(shared.get("enabled")):
        return True
    domains = shared.get("authorized_domains")
    if isinstance(domains, list):
        return "shared" in {str(item).strip() for item in domains if str(item).strip()}
    return False


def get_role_for_runtime_scope(
    workspace: Path,
    role_id: str,
) -> RoleRecord | None:
    """按 role_id 加载角色配置，用于运行时权限判断。"""

    clean_role_id = str(role_id or "").strip()
    if not clean_role_id:
        return None
    return RoleStore(Path(workspace)).get_role(clean_role_id)
