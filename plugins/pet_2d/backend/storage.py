"""Provider-owned metadata and canonical asset directories."""

from pathlib import Path
import re
import shutil
from typing import Any

from shiori_sdk.roles import Roles
from shiori_sdk.storage import plugin_data_dir

from .validation import array, digest, object_value, package_path, text

PLUGIN_ID = "pet_2d"


def role_directory(workspace: Path, role_id: str, *, create: bool = False) -> Path:
    """Resolve a role directory without following any plugin-data junction."""
    name = package_path(role_id)
    if "/" in name:
        raise ValueError("形象角色 ID 不能包含路径")
    path = workspace.resolve()
    for part in ("plugin-data", PLUGIN_ID, "models-" + name):
        path = path / part
        if path.resolve() != path or path.is_symlink():
            raise ValueError("形象素材目录越界")
        if create:
            path.mkdir(exist_ok=True)
        elif path.exists() and not path.is_dir():
            raise ValueError("形象素材目录不是文件夹")
    return path


def model_directory(workspace: Path, role_id: str, model_id: str) -> Path:
    """Model identities are hashes, never producer-controlled filesystem names."""
    digest(model_id, "model_id")
    path = role_directory(workspace, role_id) / model_id
    if path.resolve() != path:
        raise ValueError("形象模型目录越界")
    return path


def remove_owned_tree(path: Path, root: Path) -> None:
    """Delete only verified provider-owned trees, never junction targets."""
    if not path.exists():
        return
    if (
        root.resolve() != root
        or path.resolve() != path
        or path == root
        or not path.is_relative_to(root)
    ):
        raise ValueError("形象清理路径越界")
    for child in path.rglob("*"):
        if child.is_symlink() or child.resolve() != child:
            raise ValueError("形象清理目录包含链接")
    shutil.rmtree(path)


class ModelStore:
    """Store a small per-role index; full source documents remain in private files."""

    def __init__(self, roles: Roles) -> None:
        self.roles = roles

    def require_role(self, role_id: str) -> None:
        """Check both host role existence and path-safe identity."""
        if "/" in package_path(role_id) or self.roles.get_role(role_id) is None:
            raise KeyError(f"role 不存在: {role_id}")

    def list_models(self, role_id: str) -> list[dict[str, Any]]:
        """Read persisted descriptors without erasing missing or damaged files."""
        self.require_role(role_id)
        raw = object_value(
            self.roles.extensions.read(PLUGIN_ID).get(role_id, {}), "pet_2d role"
        )
        entries = array(raw.get("models", []), "stored models")
        seen = set()
        for entry in entries:
            value = object_value(entry, "stored model")
            identifier = digest(value.get("id"), "stored model id")
            if identifier in seen:
                raise ValueError("重复形象模型")
            seen.add(identifier)
            for key in ("character", "version", "display_name", "imported_at"):
                text(value.get(key), "stored " + key)
            if value.get("manifest_sha256") != identifier:
                raise ValueError("存储的形象包身份不一致")
            body = object_value(value.get("body"), "stored body")
            if any(
                type(body.get(k)) is not int or not 1 <= body[k] <= 280
                for k in ("width", "height")
            ):
                raise ValueError("存储的形象显示尺寸无效")
        return entries

    def require(self, role_id: str, model_id: str) -> dict[str, Any]:
        """Resolve model membership within one role only."""
        digest(model_id, "model_id")
        model = next(
            (entry for entry in self.list_models(role_id) if entry["id"] == model_id),
            None,
        )
        if model is None:
            raise KeyError(f"形象模型不存在: {model_id}")
        return model

    def replace(self, role_id: str, models: list[dict[str, Any]]) -> None:
        """Publish one role's detached index through the host's atomic store."""
        self.require_role(role_id)

        def save(data: dict[str, Any]) -> None:
            data[role_id] = {
                **object_value(data.get(role_id, {}), "pet_2d role"),
                "models": models,
            }

        self.roles.extensions.update(PLUGIN_ID, save)


def reconcile(roles: Roles, workspace: Path) -> None:
    """Clean deleted roles and interrupted imports, preserving indexed damaged models."""
    with roles.read_scope():
        ids = {role.id for role in roles.list_roles()}

        def prune(data):
            for role_id in list(data):
                if role_id not in ids:
                    del data[role_id]

        roles.extensions.update(PLUGIN_ID, prune)
        root = plugin_data_dir(workspace.resolve(), PLUGIN_ID)
        if not root.exists():
            return
        if root.resolve() != root:
            raise ValueError("形象素材目录越界")
        store = ModelStore(roles)
        for directory in root.glob("models-*"):
            if directory.resolve() != directory:
                raise ValueError("形象素材目录越界")
            role_id = directory.name.removeprefix("models-")
            if role_id not in ids:
                remove_owned_tree(directory, root)
                continue
            installed = {entry["id"] for entry in store.list_models(role_id)}
            for child in directory.iterdir():
                if child.name not in installed and (
                    re.fullmatch(r"[0-9a-f]{64}", child.name)
                    or child.name.startswith(".import-")
                ):
                    remove_owned_tree(child, directory)
