"""Role model selection retains the host activation context across plugin awaits."""

from __future__ import annotations


from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Literal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.roles.role_runtime import RoleRuntimeRegistry
from shiori_sdk.models import RoleModels, ModelSnapshot


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
