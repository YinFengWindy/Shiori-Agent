"""Shared role-scoped document read used by memory-plugin RPCs."""

from __future__ import annotations

from typing import Any

from .memory_service import RoleMemoryService
from .store import RoleStore


class RoleMemoryDocumentReader:
    """Validate a persisted role before reading its Markdown documents."""

    def __init__(self, role_store: RoleStore, memory: RoleMemoryService) -> None:
        self._role_store = role_store
        self._memory = memory

    async def read(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Return only the requested role's documents without initializing them."""
        role_id = str(payload.get("role_id") or "").strip()
        if self._role_store.get_role(role_id) is None:
            raise ValueError(f"role not found: {role_id}")
        return {"role_id": role_id, "documents": self._memory.read_documents(role_id)}
