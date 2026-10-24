"""Passive retrieval reads the memory engine through its getter on every turn."""

from __future__ import annotations

from typing import Any, cast

from agent.looping.ports import MemoryServices
from agent.retrieval.default_pipeline import DefaultMemoryRetrievalPipeline
from agent.retrieval.protocol import RetrievalRequest
from shiori_sdk.memory.engine import MemoryEngine, MemoryQuery, MemoryQueryResult


class _Engine:
    def __init__(self, block: str) -> None:
        self._block = block

    async def query(self, request: MemoryQuery) -> MemoryQueryResult:
        return MemoryQueryResult(text_block=self._block)


def _request() -> RetrievalRequest:
    return RetrievalRequest(
        message="hi",
        session_key="cli:1",
        channel="cli",
        chat_id="1",
        history=[],
        session_metadata={},
    )


async def test_each_retrieval_uses_the_engine_installed_at_that_time() -> None:
    installed: list[MemoryEngine | None] = [cast(Any, _Engine("old"))]
    pipeline = DefaultMemoryRetrievalPipeline(
        MemoryServices(current_engine=lambda: installed[0])
    )

    assert (await pipeline.retrieve(_request())).block == "old"
    installed[0] = cast(Any, _Engine("new"))
    assert (await pipeline.retrieve(_request())).block == "new"
    installed[0] = None
    assert (await pipeline.retrieve(_request())).block == ""
