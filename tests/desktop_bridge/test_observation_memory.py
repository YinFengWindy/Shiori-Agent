from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from desktop_bridge.observation_memory import ObservationMemoryWriter


def _writer(memory=None) -> ObservationMemoryWriter:
    return ObservationMemoryWriter(
        roles=SimpleNamespace(get_required=lambda _role_id: SimpleNamespace()),
        memory=memory or SimpleNamespace(),
    )


@pytest.mark.asyncio
async def test_remember_uses_existing_event_relationship_memory_contract() -> None:
    memory = SimpleNamespace(
        mutate=AsyncMock(
            return_value=SimpleNamespace(
                accepted=True,
                item_id="event-1",
                status="new",
                actual_kind="event",
            )
        )
    )
    writer = _writer(memory)

    result = await writer.remember(
        {
            "role_id": "mira",
            "summary": "下午一起整理了报告",
            "happened_at": "2026-07-23T12:00:00Z",
            "source_ref": "desktop-observation:session-1:0",
        }
    )

    request = memory.mutate.await_args.args[0]
    assert request.memory_kind == "event"
    assert request.memory_domain == "relationship"
    assert request.scope.role_id == "mira"
    assert request.happened_at == "2026-07-23T12:00:00Z"
    assert result == {"item_id": "event-1", "status": "new", "memory_kind": "event"}


@pytest.mark.asyncio
async def test_remember_allows_sensitive_observation_content() -> None:
    memory = SimpleNamespace(
        mutate=AsyncMock(
            return_value=SimpleNamespace(
                accepted=True,
                item_id="event-1",
                status="new",
                actual_kind="event",
            )
        )
    )
    writer = _writer(memory)

    with pytest.raises(ValueError, match="source_ref"):
        await writer.remember(
            {
                "role_id": "mira",
                "summary": "共同经历",
                "happened_at": "2026-07-23T12:00:00Z",
                "source_ref": "chat:session-1",
            }
        )
    await writer.remember(
        {
            "role_id": "mira",
            "summary": "一起查看 https://example.com",
            "happened_at": "2026-07-23T12:00:00Z",
            "source_ref": "desktop-observation:session-1:0",
        }
    )
    await writer.remember(
        {
            "role_id": "mira",
            "summary": "一起检查 user@example.com 和 C:\\Users\\name\\report.docx",
            "happened_at": "2026-07-23T12:00:00Z",
            "source_ref": "desktop-observation:session-1:1",
        }
    )

    assert [
        call.args[0].summary for call in memory.mutate.await_args_list
    ] == [
        "一起查看 https://example.com",
        "一起检查 user@example.com 和 C:\\Users\\name\\report.docx",
    ]
