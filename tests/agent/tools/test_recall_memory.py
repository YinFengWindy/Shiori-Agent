from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from agent.tools.recall_memory import RecallMemoryTool
from agent.tools.registry import ToolRegistry
from core.memory.engine import MemoryQueryResult, MemoryToolSpec


@pytest.mark.asyncio
async def test_registry_context_owns_recall_role_and_session_scope() -> None:
    memory = AsyncMock()
    memory.query.return_value = MemoryQueryResult()
    tool = RecallMemoryTool(
        memory,
        MemoryToolSpec(
            description="test recall",
            parameters={
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        ),
    )
    registry = ToolRegistry()
    registry.register(tool)
    registry.set_context(
        role_id="mira",
        session_key="role:mira",
        channel="desktop",
        chat_id="role:mira",
    )

    await registry.execute(
        "recall_memory",
        {
            "query": "secret",
            "role_id": "luna",
            "session_key": "role:luna",
            "channel": "qq",
            "chat_id": "luna-chat",
        },
    )

    request = memory.query.await_args.args[0]
    assert request.scope.role_id == "mira"
    assert request.scope.session_key == "role:mira"
    assert request.scope.channel == "desktop"
    assert request.scope.chat_id == "role:mira"
