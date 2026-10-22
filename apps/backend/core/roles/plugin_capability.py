"""The ``roles`` and ``models`` plugin capabilities over the role owners (#901 P2).

``HostRoles`` is the ``host.roles`` core service over the canonical ``RoleStore``
and ``HostRoleModels`` the ``host.models`` one over the ``RoleRuntimeRegistry``.
Each is one instance per kernel generation, shared by every plugin: neither
keeps anything per plugin.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from shiori_sdk.models import ModelSnapshot, RoleModels
from shiori_sdk.roles import Roles

if TYPE_CHECKING:
    from core.roles import RoleStore
    from core.roles.role_runtime import RoleRuntimeRegistry


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


class HostRoleModels:
    """Expose model snapshots without exporting runtime registry internals."""

    def __init__(self, registry: RoleRuntimeRegistry):
        self._registry = registry

    @asynccontextmanager
    async def activate(
        self, role_id: str, purpose: Literal["chat", "vision"]
    ) -> AsyncIterator[ModelSnapshot]:
        """Hold the exact owner-selected snapshot for the whole awaited operation."""
        runtime = await self._registry.get(role_id)
        with runtime.activate_model(purpose) as snapshot:
            yield snapshot

    def as_capability(self) -> RoleModels:
        """Validate the actual adapter against the SDK protocol."""
        return self
