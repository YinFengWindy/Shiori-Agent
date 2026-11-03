"""Typed host adapters for the memory plugin's setup surface.

``HostMemoryCapability`` is the ``host.memory`` core service (#901 P2): one
per kernel generation, shared by every plugin declaring ``memory``. The
engine is not part of this surface. A plugin provides ``MEMORY_ENGINE``
itself.
"""

from pathlib import Path

from shiori_sdk.files.text import atomic_save_text
from shiori_sdk.storage import plugin_data_dir
from agent.skills import SkillsLoader
from core.roles import RoleStore
from core.roles.memory_document_requests import RoleMemoryDocumentReader
from core.roles.memory_service import RoleMemoryService
from core.roles.policy import is_shared_memory_enabled
from infra.persistence.sqlite_lifecycle import open_owned_database


class HostMemoryStorage:
    """Resolves memory data targets and opens databases under the host lease lock."""

    def resolve_config(
        self,
        *,
        plugin_id: str,
        plugin_dir: Path,
        workspace: Path | None,
        default_text: str | None = None,
    ) -> Path:
        """Resolve local overrides, writing defaults only under the workspace."""
        if workspace is None:
            if default_text is not None:
                raise RuntimeError("创建插件配置需要 workspace，不能写入插件目录")
            return plugin_dir / "config.local.toml"
        path = plugin_data_dir(workspace, plugin_id) / "config.local.toml"
        if default_text is not None and not path.exists():
            atomic_save_text(path, default_text)
        return path

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
