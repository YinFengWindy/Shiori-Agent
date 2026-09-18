"""Durable, host-owned package previews and restart operations."""

from __future__ import annotations

import json
import os
import re
import shutil
from dataclasses import asdict, dataclass, field
from pathlib import Path
from uuid import uuid4

from agent.plugin_host.package_paths import package_path
from infra.persistence.text_store import atomic_save_text


def application_session() -> str:
    """Use the desktop lifetime, rather than the restartable bridge process."""
    return os.environ.get("SHIORI_DESKTOP_APPLICATION_SESSION_ID", "")


def owned_child(root: Path, name: str) -> Path:
    """Resolve one direct child without following package/data directory links."""
    if "/" in package_path(name, "directory"):
        raise ValueError("插件目录必须是直接子目录")
    child = root / name
    if root.resolve() != root.absolute() or child.resolve() != child.absolute():
        raise ValueError("插件操作目录不能包含链接")
    return child


def remove_owned_directory(root: Path, name: str) -> None:
    """Remove only the checked direct child owned by this operation."""
    target = owned_child(root, name)
    if target.exists():
        shutil.rmtree(target)


@dataclass
class PackageOperation:
    """A confirmed content snapshot, with a rollback directory beside its journal."""

    token: str
    plugin_id: str
    name: str
    version: str
    directory_name: str
    action: str
    session: str
    status: str = "preview"
    previous_version: str = ""
    original_fingerprint: str = ""
    staged_fingerprint: str = ""
    hashes: dict[str, str] = field(default_factory=dict)
    source_name: str = ""
    delete_data: bool = False
    error: str = ""


class PluginPackageStore:
    """Own journals outside discovery roots so incomplete packages cannot be loaded."""

    def __init__(self, workspace: Path) -> None:
        self.workspace = workspace.absolute()
        self.root = self.workspace / "private_runtime" / "plugin-operations"

    def directory(self, token: str) -> Path:
        """Return an opaque operation directory after validating its boundary."""
        if not re.fullmatch(r"[a-f0-9]{32}", token):
            raise ValueError("插件安装预览已失效，请重新选择 ZIP")
        return owned_child(self.root, token)

    def create_directory(self) -> tuple[str, Path]:
        """Allocate an exclusive staging directory on the workspace filesystem."""
        token = uuid4().hex
        directory = self.directory(token)
        directory.mkdir(parents=True)
        return token, directory

    def save(self, operation: PackageOperation) -> None:
        """Atomically persist the phase before crossing the next filesystem boundary."""
        atomic_save_text(
            self.directory(operation.token) / "operation.json",
            json.dumps(asdict(operation), ensure_ascii=False, indent=2) + "\n",
        )

    def read(self, token: str) -> PackageOperation:
        """Read one journal; malformed or missing state fails explicitly."""
        data = json.loads(
            (self.directory(token) / "operation.json").read_text(encoding="utf-8")
        )
        operation = PackageOperation(**data)
        if operation.token != token or operation.action not in {
            "install",
            "update",
            "uninstall",
        }:
            raise ValueError("插件操作记录无效")
        owned_child(self.workspace / "plugins", operation.directory_name)
        owned_child(self.workspace / "plugin-data", operation.plugin_id)
        return operation

    def list(self) -> list[PackageOperation]:
        """Return persisted operations in deterministic order."""
        if not self.root.exists():
            return []
        return [
            self.read(path.name)
            for path in sorted(self.root.iterdir())
            if (path / "operation.json").is_file()
        ]

    def remove(self, token: str) -> None:
        """Remove an owned preview or a completed operation's rollback bytes."""
        self.directory(token)
        remove_owned_directory(self.root, token)

    def remove_unjournaled_previews(self) -> None:
        """Reclaim extraction interrupted before a preview or approval was persisted."""
        if self.root.exists():
            for path in self.root.iterdir():
                if (
                    re.fullmatch(r"[a-f0-9]{32}", path.name)
                    and not (path / "operation.json").exists()
                ):
                    self.remove(path.name)

    def assert_available(self, plugin_id: str, *, except_token: str = "") -> None:
        """Reject ambiguous competing writes to one plugin ID."""
        if any(
            op.plugin_id == plugin_id
            and op.token != except_token
            and op.status == "pending"
            for op in self.list()
        ):
            raise ValueError("此插件已有待确认或待重启操作")

    def clear_failures(self, plugin_id: str) -> None:
        """A newly confirmed retry supersedes that plugin's previous diagnostic."""
        for operation in self.list():
            if operation.plugin_id == plugin_id and operation.status == "failed":
                self.remove(operation.token)
