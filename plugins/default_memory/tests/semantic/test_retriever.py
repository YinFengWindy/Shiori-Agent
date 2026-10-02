from typing import TypeAlias, cast

import pytest

from plugins.default_memory.backend.semantic.embedder import Embedder
from plugins.default_memory.backend.semantic.retriever import Retriever
from plugins.default_memory.backend.semantic.store import MemoryStore2

_MemoryHit: TypeAlias = dict[str, object]


_EmbeddingRow: TypeAlias = tuple[
    str,
    str,
    str,
    list[float] | None,
    dict[str, object],
    str | None,
    str | None,
]


class _FusionStore:
    def __init__(
        self,
        vector_groups: list[list[_MemoryHit]],
        keyword_hits: list[_MemoryHit],
    ) -> None:
        self.vector_groups = vector_groups
        self.keyword_hits = keyword_hits
        self.vector_kwargs: list[dict[str, object]] = []
        self.keyword_kwargs: list[dict[str, object]] = []

    def vector_search_batch(
        self,
        _query_vecs: list[list[float]],
        **kwargs: object,
    ) -> list[list[_MemoryHit]]:
        self.vector_kwargs.append(kwargs)
        return self.vector_groups

    def keyword_search_summary(
        self,
        _terms: list[str],
        **kwargs: object,
    ) -> list[_MemoryHit]:
        self.keyword_kwargs.append(kwargs)
        return self.keyword_hits


@pytest.mark.asyncio
async def test_retriever_returns_keyword_hits_when_vector_empty() -> None:
    store = _FusionStore(
        vector_groups=[[]],
        keyword_hits=[
            {
                "id": "kw1",
                "memory_type": "event",
                "summary": "用户处理过支付问题",
                "keyword_score": 1.0,
            }
        ],
    )
    retriever = Retriever(cast(MemoryStore2, store), cast(Embedder, _StaticEmbedder()))

    hits = await retriever.retrieve("支付", top_k=5)

    assert [item["id"] for item in hits] == ["kw1"]
    assert hits[0]["score"] == 1.0


@pytest.mark.asyncio
async def test_retriever_keeps_strong_vector_order_when_keyword_hits_are_low_rank() -> (
    None
):
    vector_hits: list[_MemoryHit] = [
        {
            "id": "vec1",
            "memory_type": "event",
            "summary": "高质量向量命中 1",
            "score": 0.95,
        },
        {
            "id": "vec2",
            "memory_type": "event",
            "summary": "高质量向量命中 2",
            "score": 0.9,
        },
    ]
    keyword_hits: list[_MemoryHit] = [
        {
            "id": f"kw{i}",
            "memory_type": "event",
            "summary": f"低排名关键词命中 {i}",
            "keyword_score": 1.0,
        }
        for i in range(12)
    ]
    store = _FusionStore(vector_groups=[vector_hits], keyword_hits=keyword_hits)
    retriever = Retriever(cast(MemoryStore2, store), cast(Embedder, _StaticEmbedder()))

    hits = await retriever.retrieve("支付", top_k=2)

    assert [item["id"] for item in hits] == ["vec1", "vec2"]


class _StaticEmbedder:
    async def embed(self, text: str) -> list[float]:
        return [1.0, 0.0]
