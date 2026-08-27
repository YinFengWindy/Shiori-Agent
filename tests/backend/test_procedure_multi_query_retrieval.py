import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from memory2.injection_planner import retrieve_procedure_items


def _make_memory_port(query_to_items: dict[str, list[dict]]):
    """mock MemoryPort：根据 query 字符串返回不同的 items。"""
    port = MagicMock()

    async def _retrieve(query, memory_types=None, top_k=None, **kwargs):
        return query_to_items.get(query, [])

    port.retrieve_related = AsyncMock(side_effect=_retrieve)
    return port


def test_multi_query_takes_max_score_for_same_item():
    """同一个 item 被多个 query 检到时，保留最高分。"""
    item_a_low = {
        "id": "item-A",
        "memory_type": "procedure",
        "score": 0.55,
        "summary": "B站下载规范",
    }
    item_a_high = {
        "id": "item-A",
        "memory_type": "procedure",
        "score": 0.72,
        "summary": "B站下载规范",
    }
    item_b = {
        "id": "item-B",
        "memory_type": "preference",
        "score": 0.60,
        "summary": "其他偏好",
    }

    port = _make_memory_port(
        {
            "把这个视频发给我": [item_a_low, item_b],
            "B站视频下载": [item_a_high],
        }
    )

    result = asyncio.run(
        retrieve_procedure_items(
            port,
            queries=["把这个视频发给我", "B站视频下载"],
            top_k=5,
        )
    )

    result_by_id = {r["id"]: r for r in result}
    assert "item-A" in result_by_id
    assert result_by_id["item-A"]["score"] == pytest.approx(0.72)


def test_multi_query_deduplicates_items():
    """同一个 item 被多个 query 检到时，最终结果里只出现一次。"""
    item = {"id": "item-X", "memory_type": "procedure", "score": 0.65, "summary": "规则X"}
    port = _make_memory_port(
        {
            "query-1": [item],
            "query-2": [item],
        }
    )

    result = asyncio.run(
        retrieve_procedure_items(port, queries=["query-1", "query-2"], top_k=5)
    )

    ids = [r["id"] for r in result]
    assert ids.count("item-X") == 1


def test_multi_query_merges_unique_items_from_different_queries():
    """不同 query 检到的不同 items，都应该出现在结果里。"""
    item_1 = {"id": "item-1", "memory_type": "procedure", "score": 0.70, "summary": "规则1"}
    item_2 = {"id": "item-2", "memory_type": "procedure", "score": 0.68, "summary": "规则2"}
    port = _make_memory_port(
        {
            "query-1": [item_1],
            "query-2": [item_2],
        }
    )

    result = asyncio.run(
        retrieve_procedure_items(port, queries=["query-1", "query-2"], top_k=5)
    )

    ids = {r["id"] for r in result}
    assert ids == {"item-1", "item-2"}


def test_single_query_string_still_works():
    """向后兼容：传单个 query 字符串也能正常运行（不能 breaking change）。"""
    item = {"id": "x", "memory_type": "procedure", "score": 0.8, "summary": "ok"}
    port = _make_memory_port({"hello": [item]})

    result = asyncio.run(retrieve_procedure_items(port, query="hello", top_k=5))
    assert len(result) == 1
