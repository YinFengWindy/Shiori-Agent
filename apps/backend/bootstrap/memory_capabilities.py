"""Typed host adapters for the memory plugin's setup surface.

``HostMemoryCapability`` is the ``host.memory`` core service (#901 P2): one
per kernel generation, shared by every plugin declaring ``memory``. The
engine is not part of this surface. A plugin provides ``MEMORY_ENGINE``
itself.
"""

from pathlib import Path

from agent.plugin_host.storage import PluginStorage
from agent.plugin_host.local_config import resolve_local_config
from agent.skills import SkillsLoader
from core.roles import RoleStore
from core.roles.memory_document_requests import RoleMemoryDocumentReader
from core.roles.memory_service import RoleMemoryService
from core.roles.policy import is_shared_memory_enabled
from infra.persistence.sqlite_lifecycle import open_owned_database


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

    def __init__(self, workspace: Path, roles: RoleStore) -> None:
        self.workspace = workspace
        self.roles = HostMemoryRoles(roles)
        self.storage = HostMemoryStorage()
        self._documents = RoleMemoryDocumentReader(roles, RoleMemoryService(workspace))

    def skill_names(self) -> list[str]:
        """Builtin and workspace skill names, including ones whose deps are unmet."""
        return [
            skill["name"]
            for skill in SkillsLoader(self.workspace).list_skills(
                filter_unavailable=False
            )
        ]

    async def read_documents(self, payload: dict[str, object]) -> dict[str, object]:
        """Validates the role and reads shared Markdown documents without mutation."""
        return await self._documents.read(payload)
