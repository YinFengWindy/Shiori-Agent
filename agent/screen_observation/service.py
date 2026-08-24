from __future__ import annotations

from typing import TYPE_CHECKING, Any

from agent.config_models import Config
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
    config: Config,
    provider: LLMProvider,
    vl_provider: LLMProvider | None,
    memory: MemoryWriteApi,
    role_runtime_registry: RoleRuntimeRegistry | None = None,
) -> ScreenObservationService:
    """Builds the default role capability with the configured visual model."""

    multimodal = bool(getattr(config, "multimodal", True))
    selected_provider = vl_provider or (provider if multimodal else None)
    selected_model = (
        str(getattr(config, "vl_model", "") or "")
        if vl_provider is not None
        else str(getattr(config, "model", "") or "")
    )
    return ScreenObservationService(
        roles=roles,
        provider=selected_provider,
        model=selected_model,
        memory=memory,
        role_runtime_registry=role_runtime_registry,
    )
