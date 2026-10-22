"""Plugin capabilities over bootstrap-owned services (#901 P2).

``HostResources`` is the ``host.resources`` core service: it resolves the
resource root of source and frozen installations. ``HostMemoryCapability`` is
the ``host.memory`` one: the memory plugin's setup surface, which injects shared
role-document reads (over the memory adapters in ``bootstrap.memory_capabilities``)
while the memory plugin owns its RPC registration. Each is one instance per
kernel generation, shared by every plugin.
"""

from pathlib import Path

from shiori_sdk.memory.engine import MemoryEngine
from shiori_sdk.processes import Resources

from bootstrap.memory_capabilities import HostMemoryRoles, HostMemoryStorage
from bootstrap.paths import common_emojis_paths, resource_root
from core.roles import RoleStore
from core.roles.memory_document_requests import RoleMemoryDocumentReader
from core.roles.memory_service import RoleMemoryService


class HostResources:
    """Resolve host-distributed resources in source and frozen installations."""

    @property
    def root(self) -> Path:
        """Return the configured host resource root."""
        return resource_root()

    def common_emojis(self, workspace: Path) -> tuple[Path, ...]:
        """Return user overrides followed by the packaged emoji resource."""
        return tuple(common_emojis_paths(workspace))

    def as_capability(self) -> Resources:
        """Validate source/frozen path access without exporting bootstrap modules."""
        return self


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
