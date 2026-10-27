"""Typed host adapters injected into memory engines and their setup surface.

``HostMemoryCapability`` is the ``host.memory`` core service (#901 P2): the
memory plugin's setup surface, one per kernel generation and shared by every
plugin declaring ``memory``.
"""

from pathlib import Path
from typing import Any

from agent.config_models import Config
from agent.plugin_host.manifest import PluginManifest
from agent.plugin_host.storage import PluginStorage
from agent.plugin_host.local_config import resolve_local_config
from core.roles import RoleStore
from core.roles.memory_document_requests import RoleMemoryDocumentReader
from core.roles.memory_service import RoleMemoryService
from core.roles.policy import is_shared_memory_enabled
from infra.persistence.sqlite_lifecycle import open_owned_database
from shiori_sdk.memory.build import EmbeddingConfig, MemoryBuildConfig
from shiori_sdk.memory.engine import MemoryEngine

from bootstrap.memory_config_migration import (
    DEFAULT_EMBEDDING_MODEL,
    DEFAULT_MEMORY_PLUGIN_ID,
    EMBEDDING_API_KEY_KEY,
    EMBEDDING_BASE_URL_KEY,
    EMBEDDING_MODEL_KEY,
    OUTPUT_DIMENSIONALITY_KEY,
    require_output_dimensionality,
)

_DEFAULT_MEMORY_MANIFEST: PluginManifest | None = None
_PLUGIN_DIMENSIONALITY = "plugins.default_memory.output_dimensionality"


class HostMemoryStorage(PluginStorage):
    """Resolves memory data targets and opens databases under the host lease lock."""

    def resolve_config(
        self,
        *,
        plugin_id: str,
        plugin_dir: Path,
        workspace: Path | None,
        default_text: str | None = None,
    ) -> Path:
        return resolve_local_config(
            plugin_id=plugin_id,
            plugin_dir=plugin_dir,
            workspace=workspace,
            default_text=default_text,
        )

    def open_database(self, path: Path):
        return open_owned_database(path, check_same_thread=False)


class HostMemoryRoles:
    """Reads role existence and explicit shared-domain policy from the owning store."""

    def __init__(self, roles: RoleStore) -> None:
        self._roles = roles

    def exists(self, role_id: str) -> bool:
        return self._roles.get_role(role_id) is not None

    def shared_memory_enabled(self, role_id: str) -> bool:
        return is_shared_memory_enabled(self._roles.get_role(role_id))


class HostMemoryCapability:
    """Explicitly typed setup surface for memory plugins."""

    def __init__(
        self, workspace: Path, roles: RoleStore, engine: MemoryEngine | None
    ) -> None:
        self.workspace = workspace
        self.engine = engine
        self.roles = HostMemoryRoles(roles)
        self.storage = HostMemoryStorage()
        self._documents = RoleMemoryDocumentReader(roles, RoleMemoryService(workspace))

    async def read_documents(self, payload: dict[str, object]) -> dict[str, object]:
        """Validates the role and reads shared Markdown documents without mutation."""
        return await self._documents.read(payload)


def default_memory_enabled(config: Config) -> bool:
    """Whether the bundled default_memory plugin is enabled for this config."""
    from agent.plugin_host.kernel import plugin_enabled

    return plugin_enabled(_default_memory_manifest(), _plugin_table(config))


def memory_build_config(config: Config) -> MemoryBuildConfig:
    """Builds engine inputs from the default_memory plugin table.

    Embedding credentials are only those stored on the plugin. Chat model
    credentials are not a fallback.
    """
    stored = _plugin_table(config)
    if EMBEDDING_MODEL_KEY in stored and stored[EMBEDDING_MODEL_KEY] is not None:
        model = str(stored[EMBEDDING_MODEL_KEY])
    else:
        model = DEFAULT_EMBEDDING_MODEL
    return MemoryBuildConfig(
        model=config.model,
        light_model=config.light_model or config.model,
        embedding=EmbeddingConfig(
            base_url=str(stored.get(EMBEDDING_BASE_URL_KEY) or ""),
            api_key=str(stored.get(EMBEDDING_API_KEY_KEY) or ""),
            model=model,
            output_dimensionality=require_output_dimensionality(
                stored.get(OUTPUT_DIMENSIONALITY_KEY),
                field=_PLUGIN_DIMENSIONALITY,
            ),
        ),
    )


def _plugin_table(config: Config) -> dict[str, Any]:
    stored = config.plugins.get(DEFAULT_MEMORY_PLUGIN_ID, {})
    return stored if isinstance(stored, dict) else {}


def _default_memory_manifest() -> PluginManifest:
    global _DEFAULT_MEMORY_MANIFEST
    if _DEFAULT_MEMORY_MANIFEST is not None:
        return _DEFAULT_MEMORY_MANIFEST
    from agent.plugin_host.manifest import load_manifest
    from bootstrap.paths import plugin_roots

    for root in plugin_roots():
        plugin_dir = root / DEFAULT_MEMORY_PLUGIN_ID
        if not (plugin_dir / "manifest.yaml").is_file():
            continue
        manifest = load_manifest(plugin_dir)
        if manifest is not None and manifest.id == DEFAULT_MEMORY_PLUGIN_ID:
            _DEFAULT_MEMORY_MANIFEST = manifest
            return manifest
    raise RuntimeError("找不到内置 default_memory 插件清单")
