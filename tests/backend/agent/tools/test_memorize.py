"""Memorize tool scope/metadata and result serialization against its public port."""

import json

from agent.tools.memorize import MemorizeTool
from shiori_sdk.memory.engine import MemoryMutationResult, MemoryToolSpec


class _Writer:
    def __init__(self):
        self.requests = []

    async def mutate(self, request):
        self.requests.append(request)
        return MemoryMutationResult(
            accepted=True, item_id="mem-1", actual_kind="preference", status="merged"
        )

    def reinforce_items_batch(self, ids):
        pass


async def test_memorize_forwards_scope_metadata_and_serializes_engine_result():
    writer = _Writer()
    tool = MemorizeTool(writer, MemoryToolSpec(description="test", parameters={}))
    result = json.loads(
        await tool.execute(
            summary="偏好",
            memory_kind="procedure",
            steps=["先查"],
            role_id="mira",
            channel="desktop",
            chat_id="1",
            session_key="role:mira",
        )
    )
    request = writer.requests[0]
    assert request.scope.role_id == "mira"
    assert request.scope.session_key == "desktop:1"
    assert request.metadata["steps"] == ["先查"]
    assert result["item_id"] == "mem-1"
    assert result["memory_kind"] == "preference"
    assert result["status"] == "merged"
