"""Desktop-pet asset ownership under the plugin data root."""

from pathlib import Path

from shiori_sdk.storage import plugin_data_dir

PLUGIN_ID = "desktop_pet"


def safe_role_id(role_id: str) -> str:
    """Reject role ids that could escape a per-role file or directory name."""
    if not role_id or role_id in {".", ".."} or any(c in role_id for c in "/\\:"):
        raise ValueError("桌宠角色 ID 不安全")
    return role_id


def role_asset_directory(workspace: Path, role_id: str) -> Path:
    """Resolve one role's pet-only directory without entering shared role assets."""
    return plugin_data_dir(workspace, PLUGIN_ID) / f"pets-{safe_role_id(role_id)}"


def asset_path(workspace: Path, value: str) -> Path:
    """Resolve only workspace-relative assets within the pet's private root."""
    root = plugin_data_dir(workspace, PLUGIN_ID).resolve()
    path = (workspace / value).resolve()
    if path == root or not path.is_relative_to(root):
        raise ValueError("桌宠素材路径越界")
    return path
