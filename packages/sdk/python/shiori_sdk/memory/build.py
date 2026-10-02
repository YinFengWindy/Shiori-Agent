"""Memory construction contracts, independent of host Config and resource scopes."""

import sqlite3
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, runtime_checkable

from shiori_sdk.http import HttpRequester
from shiori_sdk.models import ModelProvider
from shiori_sdk.runtime import EventsCapability

from .engine import MemoryAdminApi, MemoryEngine


@dataclass(frozen=True)
class EmbeddingConfig:
    """Resolved credentials and vector-space settings consumed by the engine."""

    base_url: str = ""
    api_key: str = ""
    model: str = "text-embedding-v3"
    output_dimensionality: int | None = None


@dataclass(frozen=True)
class MemoryBuildConfig:
    """Only model selection and embedding settings, already resolved by the host."""

    model: str = ""
    light_model: str = ""
    embedding: EmbeddingConfig = field(default_factory=EmbeddingConfig)


class MemoryStorage(Protocol):
    """Host-owned config migration and database leases used during construction."""

    def resolve_config(
        self,
        *,
        plugin_id: str,
        plugin_dir: Path,
        workspace: Path | None,
        default_text: str | None = None,
    ) -> Path: ...
    def migrate_data(
        self, workspace: Path, plugin_id: str, name: str, source: Path
    ) -> Path: ...
    def open_database(self, path: Path) -> sqlite3.Connection: ...


class MemoryRoles(Protocol):
    """Role existence and shared-domain authorization, without exposing RoleStore."""

    def exists(self, role_id: str) -> bool: ...
    def shared_memory_enabled(self, role_id: str) -> bool: ...


class MemoryEvents(EventsCapability, Protocol):
    """Typed hooks plus asynchronous observation queue owned by the host runtime."""

    def enqueue(self, event: object) -> None: ...
    async def fanout(self, event: object) -> None: ...


@dataclass(frozen=True)
class BuildResource:
    """One owned allocation and the cleanup selected by its creator."""

    value: object
    cleanup: Callable[[], object]


class BuildResources(Protocol):
    """Registers partial allocations and explicitly transfers successful ownership."""

    def register(self, resource: object, cleanup: Callable[[], object]) -> None: ...
    def transfer(self) -> list[BuildResource]: ...


@dataclass(frozen=True)
class MemoryPluginBuildDeps:
    """Explicit inputs for a memory engine's complete construction path."""

    config: MemoryBuildConfig
    workspace: Path
    provider: ModelProvider
    light_provider: ModelProvider | None
    requester: HttpRequester
    event_publisher: MemoryEvents | None
    storage: MemoryStorage
    roles: MemoryRoles
    skills: Callable[[], list[str]]
    resources: BuildResources


@dataclass
class MemoryPluginRuntime:
    """A completed engine and the resources transferred to its runtime owner."""

    engine: MemoryEngine
    closeables: list[object] = field(default_factory=list)
    admin: MemoryAdminApi | None = None
    resources: list[BuildResource] = field(default_factory=list)


class MemoryStorageIncompatibleError(ValueError):
    """The requested vector space requires an explicit persistent-data migration."""

    code = "memory_storage_incompatible"

    def to_details(self):
        """Supplies a non-secret recovery hint to the settings UI."""
        return {"code": self.code, "reason": "embedding_migration_required"}


@runtime_checkable
class MemoryPlugin(Protocol):
    """Build and compatibility entrypoints of an independently installed engine."""

    plugin_id: str

    def build(self, deps: MemoryPluginBuildDeps) -> MemoryPluginRuntime: ...
    def validate_transition(
        self,
        previous: MemoryBuildConfig,
        candidate: MemoryBuildConfig,
        workspace: Path,
        storage: MemoryStorage,
    ) -> None: ...
    def ensure_workspace_storage(
        self, *, config: MemoryBuildConfig, workspace: Path, storage: MemoryStorage
    ) -> list[tuple[Path, bool]]: ...
