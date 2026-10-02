from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, TypeAlias, cast
from zoneinfo import ZoneInfo

import pytest


def _as_record_retrieval_baseline(value: object) -> dict[str, object]:
    return cast(dict[str, object], value)


def _now_retrieval_baseline() -> datetime:
    return datetime.now(timezone.utc)


def _days_ago_retrieval_baseline(n: int) -> str:
    return (_now_retrieval_baseline() - timedelta(days=n)).isoformat()


def test_baseline_cosine_ranking_basic(tmp_path, make_store):
    """[PASS] vector_search 按 cosine 相似度降序返回结果。"""
    store = make_store(tmp_path / "m.db")

    store.upsert_item("preference", "高相似条目 A", embedding=[1.0, 0.0, 0.0], extra={})
    store.upsert_item(
        "procedure", "中等相似条目 B", embedding=[0.8, 0.6, 0.0], extra={}
    )
    store.upsert_item("event", "低相似条目 C", embedding=[0.0, 1.0, 0.0], extra={})

    # 查询向量与 A 最相似，与 C 正交
    results = cast(
        list[dict[str, object]],
        store.vector_search(query_vec=[1.0, 0.0, 0.0], top_k=3, score_threshold=0.0),
    )

    assert len(results) == 3
    assert _as_record_retrieval_baseline(results[0])["summary"] == "高相似条目 A"
    score0 = cast(float, _as_record_retrieval_baseline(results[0])["score"])
    score1 = cast(float, _as_record_retrieval_baseline(results[1])["score"])
    score2 = cast(float, _as_record_retrieval_baseline(results[2])["score"])
    assert score0 >= score1 >= score2


def test_baseline_superseded_excluded_from_retrieval(tmp_path, make_store):
    """[PASS] superseded 条目不出现在检索结果中（include_superseded=False）。"""
    store = make_store(tmp_path / "m.db")

    store.upsert_item("procedure", "旧规则（已退休）", embedding=[1.0, 0.0], extra={})
    old_id = store.list_by_type("procedure")[0]["id"]
    store.mark_superseded(cast(Any, old_id))

    store.upsert_item("procedure", "新规则（active）", embedding=[0.9, 0.0], extra={})

    results = store.vector_search(query_vec=[1.0, 0.0], top_k=5, score_threshold=0.0)
    summaries = [r["summary"] for r in results]

    assert "旧规则（已退休）" not in summaries, "superseded 条目不应出现在检索结果中"
    assert "新规则（active）" in summaries


def test_baseline_score_threshold_filters_low_matches(tmp_path, make_store):
    """[PASS] score_threshold 过滤低相似度条目。"""
    store = make_store(tmp_path / "m.db")

    # 条目 A：与查询高度相似
    store.upsert_item("preference", "相关条目", embedding=[1.0, 0.0, 0.0], extra={})
    # 条目 B：与查询几乎正交（cosine ≈ 0）
    store.upsert_item("preference", "不相关条目", embedding=[0.0, 1.0, 0.0], extra={})

    results = store.vector_search(
        query_vec=[1.0, 0.0, 0.0],
        top_k=5,
        score_threshold=0.5,  # 过滤低分
    )

    summaries = [r["summary"] for r in results]
    assert "相关条目" in summaries
    assert "不相关条目" not in summaries


def test_baseline_top_k_limits_result_count(tmp_path, make_store):
    """[PASS] top_k 限制返回数量。"""
    store = make_store(tmp_path / "m.db")

    for i in range(10):
        store.upsert_item(
            "event", f"条目 {i}", embedding=[1.0 - i * 0.05, 0.0], extra={}
        )

    results = store.vector_search(query_vec=[1.0, 0.0], top_k=3, score_threshold=0.0)
    assert len(results) == 3


def test_baseline_type_filter_works(tmp_path, make_store):
    """[PASS] memory_types 过滤只返回指定类型。"""
    store = make_store(tmp_path / "m.db")

    store.upsert_item("procedure", "procedure 条目", embedding=[1.0, 0.0], extra={})
    store.upsert_item("preference", "preference 条目", embedding=[0.99, 0.01], extra={})

    results = store.vector_search(
        query_vec=[1.0, 0.0],
        top_k=5,
        memory_types=["procedure"],
        score_threshold=0.0,
    )

    assert all(r["memory_type"] == "procedure" for r in results)
    assert len(results) == 1


def test_boundary_high_reinforcement_not_boosted(tmp_path, make_store):
    """[BOUNDARY] 高 reinforcement 条目不会因频繁访问而排名靠前。

    场景：
      条目 A：semantic=0.90，被用户反复确认（reinforcement=10），昨天刚用过
      条目 B：semantic=0.95，只创建过一次（reinforcement=1），30 天前

    直觉上 A 更"有用"（被持续验证，且新鲜），但当前纯 cosine 排序中 B 靠前。

    当前行为：B 排在 A 前面（score_B=0.95 > score_A=0.90）。

    优化后预期（hotness_alpha=0.18, half_life=14天）：
      hotness_A = sigmoid(log1p(10)) * exp(-ln2/14*1) ≈ 0.855 * 0.951 ≈ 0.813
      hotness_B = sigmoid(log1p(1))  * exp(-ln2/14*30) ≈ 0.574 * 0.228 ≈ 0.131
      final_A = 0.82*0.90 + 0.18*0.813 ≈ 0.738 + 0.146 = 0.884
      final_B = 0.82*0.95 + 0.18*0.131 ≈ 0.779 + 0.024 = 0.803
      → A(0.884) > B(0.803)，A 应排前。
      断言应改为 assert results[0]["summary"] == "条目 A（常用且新鲜）"
    """
    store = make_store(tmp_path / "m.db")

    # 条目 A：与查询相似度 0.90，reinforcement=10，1天前更新
    store.upsert_item(
        "procedure",
        "条目 A（常用且新鲜）",
        embedding=[
            0.90,
            0.436,
            0.0,
        ],  # cosine([1,0,0], [0.9,0.436,0]) = 0.9/sqrt(0.81+0.19) = 0.9
        extra={},
    )
    item_a_id = store.list_by_type("procedure")[0]["id"]
    # 手动设置 reinforcement=10，updated_at=昨天
    store._db.execute(
        "UPDATE memory_items SET reinforcement=10, updated_at=? WHERE id=?",
        (_days_ago_retrieval_baseline(1), item_a_id),
    )
    store._db.commit()

    # 条目 B：与查询相似度 0.95，reinforcement=1，30天前创建
    store.upsert_item(
        "procedure",
        "条目 B（一次性，陈旧）",
        embedding=[
            0.95,
            0.312,
            0.0,
        ],  # cosine([1,0,0], [0.95,0.312,0]) = 0.95/sqrt(0.9025+0.097) ≈ 0.95
        extra={},
    )
    item_b_id = [
        r["id"] for r in store.list_by_type("procedure") if r["id"] != item_a_id
    ][0]
    store._db.execute(
        "UPDATE memory_items SET reinforcement=1, created_at=?, updated_at=? WHERE id=?",
        (_days_ago_retrieval_baseline(30), _days_ago_retrieval_baseline(30), item_b_id),
    )
    store._db.commit()

    results = store.vector_search(
        query_vec=[1.0, 0.0, 0.0],
        top_k=5,
        score_threshold=0.0,
        # hotness_alpha 未传入（当前接口不支持），纯 cosine 模式
    )

    assert len(results) == 2

    # ── CURRENT BEHAVIOR ──
    # 纯 cosine：B(0.95) > A(0.90)，B 排前
    assert results[0]["summary"] == "条目 B（一次性，陈旧）", (
        "CURRENT: 纯 cosine 排序，高语义分的陈旧条目 B 排在常用新鲜条目 A 前。"
        " 优化后（hotness_alpha=0.18）：final_score_A=0.884 > final_score_B=0.803，"
        "A 应排前，断言改为 results[0]['summary'] == '条目 A（常用且新鲜）'"
    )
    assert results[1]["summary"] == "条目 A（常用且新鲜）"


def test_boundary_recent_update_not_boosted(tmp_path, make_store):
    """[BOUNDARY] 最近被更新（验证）的条目不因 recency 而排名靠前。

    场景：
      条目 A：semantic=0.88，2天前刚被 reinforced
      条目 B：semantic=0.92，60天前创建后再未被使用

    当前行为：B 排前（纯 cosine 0.92 > 0.88）。

    优化后预期（hotness_alpha=0.18, half_life=14天）：
      hotness_A = sigmoid(log1p(3)) * exp(-ln2/14*2) ≈ 0.757 * 0.906 ≈ 0.686
      hotness_B = sigmoid(log1p(1)) * exp(-ln2/14*60) ≈ 0.574 * 0.054 ≈ 0.031
      final_A = 0.82*0.88 + 0.18*0.686 ≈ 0.722 + 0.123 = 0.845
      final_B = 0.82*0.92 + 0.18*0.031 ≈ 0.754 + 0.006 = 0.760
      → A 排前，断言应改为 results[0]['summary'] == '条目 A（近期使用）'
    """
    store = make_store(tmp_path / "m.db")

    # 条目 A：semantic≈0.88，reinforcement=3，2天前
    store.upsert_item(
        "preference",
        "条目 A（近期使用）",
        embedding=[0.88, 0.475, 0.0],
        extra={},
    )
    item_a_id = store.list_by_type("preference")[0]["id"]
    store._db.execute(
        "UPDATE memory_items SET reinforcement=3, updated_at=? WHERE id=?",
        (_days_ago_retrieval_baseline(2), item_a_id),
    )
    store._db.commit()

    # 条目 B：semantic≈0.92，reinforcement=1，60天前
    store.upsert_item(
        "preference",
        "条目 B（陈旧未用）",
        embedding=[0.92, 0.392, 0.0],
        extra={},
    )
    item_b_id = [
        r["id"] for r in store.list_by_type("preference") if r["id"] != item_a_id
    ][0]
    store._db.execute(
        "UPDATE memory_items SET reinforcement=1, created_at=?, updated_at=? WHERE id=?",
        (_days_ago_retrieval_baseline(60), _days_ago_retrieval_baseline(60), item_b_id),
    )
    store._db.commit()

    results = store.vector_search(
        query_vec=[1.0, 0.0, 0.0],
        top_k=5,
        score_threshold=0.0,
    )

    # ── CURRENT BEHAVIOR ──
    assert results[0]["summary"] == "条目 B（陈旧未用）", (
        "CURRENT: 纯 cosine，B(0.92)排前。"
        " 优化后：final_A(0.845) > final_B(0.760)，A 应排前。"
    )


def test_boundary_score_does_not_include_hotness_fields(tmp_path, make_store):
    """[OPTIMIZED] vector_search 现在始终返回 _score_debug 字段，
    包含 semantic/hotness/final 三个拆分分数，便于观测和调试。
    """
    store = make_store(tmp_path / "m.db")
    store.upsert_item("event", "测试条目", embedding=[1.0, 0.0], extra={})

    results = store.vector_search(query_vec=[1.0, 0.0], top_k=1, score_threshold=0.0)
    assert len(results) == 1

    debug = cast(
        dict[str, object] | None,
        _as_record_retrieval_baseline(results[0]).get("_score_debug"),
    )
    assert debug is not None, "优化后：_score_debug 字段应始终存在"
    assert "semantic" in debug
    assert "hotness" in debug
    assert "final" in debug
    # hotness_alpha=0（默认）时，hotness 分量为 0，final == semantic
    score_debug = cast(dict[str, float], debug)
    assert score_debug["hotness"] == 0.0
    assert abs(score_debug["final"] - score_debug["semantic"]) < 1e-6


def test_emotional_weight_extends_hotness_half_life_in_ranking(tmp_path, make_store):
    store = make_store(tmp_path / "m.db")
    age = _days_ago_retrieval_baseline(20)

    low = store.upsert_item(
        "event",
        "普通事件",
        embedding=[0.88, 0.475, 0.0],
        extra={},
        emotional_weight=0,
    )
    high = store.upsert_item(
        "event",
        "情绪事件",
        embedding=[0.88, 0.475, 0.0],
        extra={},
        emotional_weight=8,
    )
    low_id = low.split(":", 1)[1]
    high_id = high.split(":", 1)[1]
    store._db.execute(
        "UPDATE memory_items SET reinforcement=3, updated_at=? WHERE id IN (?, ?)",
        (age, low_id, high_id),
    )
    store._db.commit()

    results = store.vector_search(
        query_vec=[1.0, 0.0, 0.0],
        top_k=2,
        score_threshold=0.0,
        hotness_alpha=0.20,
    )

    assert results[0]["summary"] == "情绪事件"
    assert (
        cast(
            dict[str, float],
            _as_record_retrieval_baseline(results[0]).get("_score_debug", {}),
        )["hotness"]
        > cast(
            dict[str, float],
            _as_record_retrieval_baseline(results[1]).get("_score_debug", {}),
        )["hotness"]
    )


def test_vector_search_filters_memory_type(tmp_path: Path, make_store):
    store = make_store(tmp_path / "mem.db")
    try:
        store.upsert_consolidation_event(
            source_ref="r1", summary="Event A", embedding=[0.0, 1.0]
        )
        store.upsert_item(
            "procedure",
            "Use pacman",
            [1.0, 0.0],
            extra={
                "trigger_tags": {
                    "scope": "tool_triggered",
                    "tools": [],
                    "skills": [],
                    "keywords": ["pacman"],
                }
            },
        )

        results = store.vector_search([0.0, 1.0], top_k=2, memory_types=["event"])

        assert results and results[0]["memory_type"] == "event"
        assert store.list_by_type("event")
    finally:
        store.close()


_EmbeddingRow_temporal_retrieval: TypeAlias = tuple[
    str,
    str,
    str,
    list[float] | None,
    dict[str, object],
    str | None,
    str | None,
]


def test_store_vector_search_respects_time_range(tmp_path: Path, make_store) -> None:
    store = make_store(tmp_path / "memory2.db")
    tz = ZoneInfo("Asia/Shanghai")
    store.upsert_item(
        "event",
        "[2026-04-25 01:30] DeepSeek 今日事件",
        [1.0, 0.0],
        happened_at="2026-04-24T17:30:00+00:00",
    )
    store.upsert_item(
        "event",
        "[2026-04-24 23:00] DeepSeek 昨日事件",
        [1.0, 0.0],
        happened_at="2026-04-24T23:00:00",
    )

    start = datetime(2026, 4, 25, 0, 0, tzinfo=tz)
    end = datetime(2026, 4, 26, 0, 0, tzinfo=tz)
    vector_hits = store.vector_search(
        [1.0, 0.0],
        top_k=5,
        memory_types=["event"],
        score_threshold=0.0,
        time_start=start,
        time_end=end,
    )
    assert [item["summary"] for item in vector_hits] == [
        "[2026-04-25 01:30] DeepSeek 今日事件"
    ]


def test_store_vector_batch_reuses_time_filtered_embedding_rows(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    make_store,
) -> None:
    store = make_store(tmp_path / "memory2.db")
    tz = ZoneInfo("Asia/Shanghai")
    store.upsert_item(
        "event",
        "[2026-04-25 09:00] DeepSeek 今日事件",
        [1.0, 0.0],
        happened_at="2026-04-25T09:00:00",
    )
    store.upsert_item(
        "event",
        "[2026-04-25 10:00] 重构今日事件",
        [0.0, 1.0],
        happened_at="2026-04-25T10:00:00",
    )
    calls = 0
    original = store._get_embedding_rows_by_time_filter

    def counted_get_embedding_rows_by_time_filter(
        *,
        memory_types: list[str] | None,
        memory_domains: list[str] | None,
        include_superseded: bool,
        role_id: str | None,
        scope_channel: str | None,
        scope_chat_id: str | None,
        require_scope_match: bool,
        time_start: datetime | None,
        time_end: datetime | None,
    ) -> list[_EmbeddingRow_temporal_retrieval]:
        nonlocal calls
        calls += 1
        return original(
            memory_types=memory_types,
            memory_domains=memory_domains,
            include_superseded=include_superseded,
            role_id=role_id,
            scope_channel=scope_channel,
            scope_chat_id=scope_chat_id,
            require_scope_match=require_scope_match,
            time_start=time_start,
            time_end=time_end,
        )

    monkeypatch.setattr(
        store,
        "_get_embedding_rows_by_time_filter",
        counted_get_embedding_rows_by_time_filter,
    )

    results = store.vector_search_batch(
        [[1.0, 0.0], [0.0, 1.0], [1.0, 0.0]],
        top_k=2,
        score_threshold=0.0,
        time_start=datetime(2026, 4, 25, 0, 0, tzinfo=tz),
        time_end=datetime(2026, 4, 26, 0, 0, tzinfo=tz),
    )

    assert calls == 1
    assert len(results) == 3
    assert results[0][0]["summary"] == "[2026-04-25 09:00] DeepSeek 今日事件"
    assert results[1][0]["summary"] == "[2026-04-25 10:00] 重构今日事件"
