"""Inject shared role-document reads while the memory plugin owns RPC registration."""

from pathlib import Path

from bootstrap.memory_capabilities import HostMemoryRoles, HostMemoryStorage
from core.roles import RoleStore
from core.roles.memory_document_requests import RoleMemoryDocumentReader
from core.roles.memory_service import RoleMemoryService
from shiori_sdk.memory.engine import MemoryEngine


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
