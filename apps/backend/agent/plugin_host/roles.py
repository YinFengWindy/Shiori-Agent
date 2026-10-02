"""Narrow role/asset access backed by the canonical role store."""

from __future__ import annotations


from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.roles import RoleStore
from shiori_sdk.roles import Roles


class HostRoles:
    """Expose snapshots and asset writes while retaining the owner's single lock."""

    def __init__(self, store: RoleStore):
        self._store = store

    def get_role(self, role_id: str):
        """Return a detached persisted role snapshot."""
        return self._store.get_role(role_id)

    def list_roles(self):
        """Return detached current roles."""
        return self._store.list_roles()

    def asset_path(self, relative_path: str) -> Path:
        """Resolve an asset through the owner's root, not plugin path guesses."""
        return self._store.roles_dir / relative_path

    def add_illustration(self, role_id: str, source: Path) -> str:
        """Adopt a generated asset using the role owner's normal save flow."""
        return self._store.update_role(
            role_id, illustration_sources=[source]
        ).illustrations[-1]

    def set_chat_background(self, role_id: str, path: str) -> bool:
        """Persist the selected role background."""
        return (
            path in self._store.update_role(role_id, chat_background=path).illustrations
        )

    def read_scope(self):
        """Keep a multi-read extension reconciliation atomic against role edits."""
        return self._store.lock

    @property
    def extensions(self):
        """Opaque plugin namespaces use the same canonical manifest transaction."""
        return self._store.extensions

    def as_capability(self) -> Roles:
        """Check the real implementation at the host injection boundary."""
        return self
