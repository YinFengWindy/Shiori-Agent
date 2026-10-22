"""Typed host adapters injected into memory engines and their setup surface.

``HostMemoryCapability`` is the ``host.memory`` core service (#901 P2): the
memory plugin's setup surface, one per kernel generation and shared by every
plugin declaring ``memory``.
"""

from pathlib import Path

from agent.config_models import Config
from agent.plugin_host.storage import PluginStorage
from agent.plugin_host.local_config import resolve_local_config
from core.roles import RoleStore
from core.roles.memory_document_requests import RoleMemoryDocumentReader
from core.roles.memory_service import RoleMemoryService
from core.roles.policy import is_shared_memory_enabled
from infra.persistence.sqlite_lifecycle import open_owned_database
from shiori_sdk.memory.build import EmbeddingConfig, MemoryBuildConfig
from shiori_sdk.memory.engine import MemoryEngine


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


def memory_build_config(config: Config) -> MemoryBuildConfig:
    """Resolves credential fallback before passing bounded values to the plugin."""
    embedding = config.memory.embedding
    return MemoryBuildConfig(
        model=config.model,
        light_model=config.light_model or config.model,
        embedding=EmbeddingConfig(
            base_url=embedding.base_url
            or config.light_base_url
            or config.base_url
            or "",
            api_key=embedding.api_key or config.light_api_key or config.api_key,
            model=embedding.model,
            output_dimensionality=embedding.output_dimensionality,
        ),
    )
