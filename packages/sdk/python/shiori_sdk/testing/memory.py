"""Small memory capability fakes; none imports or constructs a host service."""

import sqlite3
from pathlib import Path

from shiori_sdk.storage import plugin_data_dir


class FakeMemoryRoles:
    """Role existence and explicit authorization represented as sets."""

    def __init__(self, roles: tuple[str, ...] = (), shared: tuple[str, ...] = ()):
        self.roles = set(roles)
        self.shared = set(shared)

    def exists(self, role_id: str) -> bool:
        return role_id in self.roles

    def shared_memory_enabled(self, role_id: str) -> bool:
        return role_id in self.shared


class FakeMemoryStorage:
    """Resolves test-owned paths, leaving real migration behavior to host tests."""

    def resolve_config(
        self,
        *,
        plugin_id: str,
        plugin_dir: Path,
        workspace: Path | None,
        default_text: str | None = None,
    ) -> Path:
        path = (
            plugin_data_dir(workspace, plugin_id) if workspace else plugin_dir
        ) / "config.local.toml"
        if default_text is not None and not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(default_text, encoding="utf-8")
        return path

    def migrate_data(
        self, workspace: Path, plugin_id: str, name: str, source: Path
    ) -> Path:
        return plugin_data_dir(workspace, plugin_id) / name

    def open_database(self, path: Path) -> sqlite3.Connection:
        return sqlite3.connect(path, check_same_thread=False)
