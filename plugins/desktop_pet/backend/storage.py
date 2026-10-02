"""Desktop-pet asset ownership and migration under the role transaction lock."""

from pathlib import Path

from shiori_sdk.extensions import PrivateStorage
from shiori_sdk.storage import plugin_data_dir
from shiori_sdk.roles import Roles

PLUGIN_ID = "desktop_pet"


def role_asset_directory(workspace: Path, role_id: str) -> Path:
    """Resolve one role's pet-only directory without entering shared role assets."""
    if not role_id or role_id in {".", ".."} or any(c in role_id for c in "/\\:"):
        raise ValueError("桌宠角色 ID 不安全")
    return plugin_data_dir(workspace, PLUGIN_ID) / f"pets-{role_id}"


def asset_path(workspace: Path, value: str) -> Path:
    """Resolve only workspace-relative assets within the pet's private root."""
    root = plugin_data_dir(workspace, PLUGIN_ID).resolve()
    path = (workspace / value).resolve()
    if path == root or not path.is_relative_to(root):
        raise ValueError("桌宠素材路径越界")
    return path


def prepare_assets(roles: Roles, workspace: Path, storage: PrivateStorage) -> None:
    """Copy legacy bytes before atomically publishing every package's new paths."""
    with roles.read_scope():
        data = roles.extensions.read(PLUGIN_ID)
        current_ids = {role.id for role in roles.list_roles()}
        changed = False
        for role_id in current_ids:
            state = data.get(role_id, {})
            target = role_asset_directory(workspace, role_id)
            target = storage.migrate_data(
                workspace,
                PLUGIN_ID,
                target.name,
                roles.asset_path(f"assets/{role_id}/pets"),
            )
            prefix = f"assets/{role_id}/pets/"
            for package in state.get("pet_packages", []):
                for key in ("manifest_path", "spritesheet_path", "preview_path"):
                    value = package.get(key)
                    if isinstance(value, str) and value.startswith(prefix):
                        resolved = (target / value.removeprefix(prefix)).resolve()
                        if not resolved.is_relative_to(target.resolve()):
                            raise ValueError("桌宠迁移素材路径越界")
                        package[key] = resolved.relative_to(
                            workspace.resolve()
                        ).as_posix()
                        changed = True
        if changed:

            def replace(namespace):
                namespace.clear()
                namespace.update(data)

            roles.extensions.update(PLUGIN_ID, replace)
