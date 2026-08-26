from __future__ import annotations

from typing import TYPE_CHECKING, Any

from agent.provider import LLMProvider
from core.memory.engine import MemoryWriteApi
from core.roles import RoleRepository
from agent.screen_observation.memory import ObservationMemoryWriter
from agent.screen_observation.model import ObservationModelAdapter

if TYPE_CHECKING:
    from core.roles.role_runtime import RoleRuntimeRegistry


class ScreenObservationService:
    """Composes role screen analysis and common-memory episode persistence."""

    def __init__(
        self,
        *,
        roles: RoleRepository,
        provider: LLMProvider | None,
        model: str,
        memory: MemoryWriteApi,
        role_runtime_registry: RoleRuntimeRegistry | None = None,
    ) -> None:
        self._model_adapter = ObservationModelAdapter(
            roles=roles,
            provider=provider,
            model=model,
            role_runtime_registry=role_runtime_registry,
        )
        self._memory_writer = ObservationMemoryWriter(
            roles=roles,
            memory=memory,
        )

    async def analyze(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Delegates an ephemeral frame to the observation model adapter."""

        return await self._model_adapter.analyze(payload)

    async def remember(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Delegates a settled episode to the common memory writer."""

        return await self._memory_writer.remember(payload)


def build_screen_observation_service(
    *,
    roles: RoleRepository,
    memory: MemoryWriteApi,
    role_runtime_registry: RoleRuntimeRegistry,
) -> ScreenObservationService:
    """Builds the default role capability with role-owned visual selection."""

    return ScreenObservationService(
        roles=roles,
        provider=None,
        model="",
        memory=memory,
        role_runtime_registry=role_runtime_registry,
    )
