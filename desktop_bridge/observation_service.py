from __future__ import annotations

from typing import Any

from agent.provider import LLMProvider
from core.memory.engine import MemoryWriteApi
from core.roles import RoleRepository
from desktop_bridge.observation_memory import ObservationMemoryWriter
from desktop_bridge.observation_model import ObservationModelAdapter


class DesktopObservationService:
    """Composes observation analysis and common-memory episode persistence."""

    def __init__(
        self,
        *,
        roles: RoleRepository,
        provider: LLMProvider,
        model: str,
        memory: MemoryWriteApi,
    ) -> None:
        self._model_adapter = ObservationModelAdapter(
            roles=roles,
            provider=provider,
            model=model,
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
