"""Narrow ports the memory capability exposes to a plugin.

These are the host-owned role, storage and event surfaces a memory plugin
reads during setup. Engine construction itself is the plugin's ``setup``:
it ``provide``s ``MEMORY_ENGINE`` and is not described here.
"""

import sqlite3
from pathlib import Path
from typing import Protocol

from shiori_sdk.extensions import PrivateStorage
from shiori_sdk.runtime import EventsCapability


class MemoryStorage(PrivateStorage, Protocol):
    """Host-owned config migration and database leases used by a memory plugin."""

    def resolve_config(
        self,
        *,
        plugin_id: str,
        plugin_dir: Path,
        workspace: Path | None,
        default_text: str | None = None,
    ) -> Path: ...
    def open_database(self, path: Path) -> sqlite3.Connection: ...


class MemoryRoles(Protocol):
    """Role existence and shared-domain authorization, without exposing RoleStore."""

    def exists(self, role_id: str) -> bool: ...
    def shared_memory_enabled(self, role_id: str) -> bool: ...


class MemoryEvents(EventsCapability, Protocol):
    """Typed hooks plus the host runtime's asynchronous observation queue."""

    def enqueue(self, event: object) -> None: ...
    async def fanout(self, event: object) -> None: ...
