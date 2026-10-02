"""Disabled host engine and imports of the SDK build contracts."""

from __future__ import annotations

from datetime import datetime

from shiori_sdk.memory.engine import (
    EngineProfile,
    MemoryEngine,
    MemoryEngineDescriptor,
    MemoryIngestRequest,
    MemoryIngestResult,
    MemoryMutation,
    MemoryMutationResult,
    MemoryQuery,
    MemoryQueryResult,
    MemoryToolProfile,
)


class DisabledMemoryEngine(MemoryEngine):
    DESCRIPTOR = MemoryEngineDescriptor(
        name="disabled",
        profile=EngineProfile.CONTEXT_RESOURCE_ENGINE,
        capabilities=frozenset(),
        notes={"reason": "semantic memory disabled"},
    )

    async def ingest(self, request: MemoryIngestRequest) -> MemoryIngestResult:
        return MemoryIngestResult(accepted=False, raw={"reason": "disabled"})

    async def query(
        self,
        request: MemoryQuery,
    ) -> MemoryQueryResult:
        return MemoryQueryResult(trace={"mode": "disabled", "intent": request.intent})

    async def mutate(self, request: MemoryMutation) -> MemoryMutationResult:
        if request.kind == "forget":
            return MemoryMutationResult(
                accepted=False,
                status="disabled",
                missing_ids=list(request.ids),
            )
        return MemoryMutationResult(accepted=False, status="disabled")

    def reinforce_items_batch(self, ids: list[str]) -> None:
        return None

    def list_role_filter_values(self, role_id: str) -> dict[str, list[str]]:
        return {}

    def describe(self) -> MemoryEngineDescriptor:
        return self.DESCRIPTOR

    def tool_profile(self) -> MemoryToolProfile:
        return MemoryToolProfile()

    def keyword_match_procedures(
        self,
        action_tokens: list[str],
    ) -> list[dict[str, object]]:
        return []

    def list_events_by_time_range(
        self,
        time_start: datetime,
        time_end: datetime,
        *,
        limit: int = 200,
    ) -> list[dict[str, object]]:
        return []

    def list_items_for_admin(
        self,
        *,
        q: str = "",
        memory_type: str = "",
        memory_domain: str = "",
        role_id: str = "",
        status: str = "",
        source_ref: str = "",
        scope_channel: str = "",
        scope_chat_id: str = "",
        has_embedding: bool | None = None,
        page: int = 1,
        page_size: int = 50,
        sort_by: str = "created_at",
        sort_order: str = "desc",
    ) -> tuple[list[dict[str, object]], int]:
        return [], 0

    def get_item_for_admin(
        self,
        item_id: str,
        *,
        include_embedding: bool = False,
    ) -> dict[str, object] | None:
        return None

    def update_item_for_admin(
        self,
        item_id: str,
        *,
        status: str | None = None,
        extra_json: dict[str, object] | None = None,
        source_ref: str | None = None,
        happened_at: str | None = None,
        emotional_weight: int | None = None,
    ) -> dict[str, object] | None:
        return None

    def delete_item(self, item_id: str) -> bool:
        return False

    def delete_items_batch(self, ids: list[str]) -> int:
        return 0

    def invalidate_role_memories(self, role_id: str) -> int:
        """Treat disabled memory invalidation as a successful no-op."""

        return 0

    def find_similar_items_for_admin(
        self,
        item_id: str,
        *,
        top_k: int = 8,
        memory_type: str = "",
        score_threshold: float = 0.0,
        include_superseded: bool = False,
    ) -> list[dict[str, object]]:
        return []
