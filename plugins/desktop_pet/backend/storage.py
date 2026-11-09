"""Desktop-pet private data identity and safe role file names."""

PLUGIN_ID = "desktop_pet"


def safe_role_id(role_id: str) -> str:
    """Reject role ids that could escape a per-role file or directory name."""
    if not role_id or role_id in {".", ".."} or any(c in role_id for c in "/\\:"):
        raise ValueError("桌宠角色 ID 不安全")
    return role_id
