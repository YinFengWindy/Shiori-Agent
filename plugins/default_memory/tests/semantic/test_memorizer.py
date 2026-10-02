from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, cast

import pytest
from shiori_sdk.testing.memory import FakeMemoryStorage

from plugins.default_memory.backend.semantic.memorizer import (
    Memorizer,
    _parse_history_entry_happened_at,
)
from plugins.default_memory.backend.semantic.store import MemoryStore2


@pytest.mark.asyncio
async def test_memorizer_profile_supersede_keeps_high_emotional_weight_item_under_092():
    class _Embedder:
        async def embed(self, text: str) -> list[float]:
            mapping = {
                "用户仍在等待 offer": [1.0, 0.0],
                "用户开始等待新的 offer": [0.91, 0.4146],
            }
            return mapping[text]

    store = MemoryStore2(":memory:", open_database=FakeMemoryStorage().open_database)
    memorizer = Memorizer(store, cast(Any, _Embedder()))

    await memorizer.save_item(
        summary="用户仍在等待 offer",
        memory_type="profile",
        extra={"category": "status"},
        source_ref="old",
        emotional_weight=8,
    )
    await memorizer.save_item_with_supersede(
        summary="用户开始等待新的 offer",
        memory_type="profile",
        extra={"category": "status"},
        source_ref="new",
    )

    rows = store._db.execute(
        "SELECT source_ref, status FROM memory_items WHERE memory_type='profile' ORDER BY source_ref"
    ).fetchall()
    assert rows == [("new", "active"), ("old", "active")]


@pytest.mark.asyncio
async def test_memorizer_profile_supersede_retires_low_emotional_weight_item_at_091():
    class _Embedder:
        async def embed(self, text: str) -> list[float]:
            mapping = {
                "用户仍在等待 offer": [1.0, 0.0],
                "用户开始等待新的 offer": [0.91, 0.4146],
            }
            return mapping[text]

    store = MemoryStore2(":memory:", open_database=FakeMemoryStorage().open_database)
    memorizer = Memorizer(store, cast(Any, _Embedder()))

    await memorizer.save_item(
        summary="用户仍在等待 offer",
        memory_type="profile",
        extra={"category": "status"},
        source_ref="old",
        emotional_weight=0,
    )
    await memorizer.save_item_with_supersede(
        summary="用户开始等待新的 offer",
        memory_type="profile",
        extra={"category": "status"},
        source_ref="new",
    )

    rows = store._db.execute(
        "SELECT source_ref, status FROM memory_items WHERE memory_type='profile' ORDER BY source_ref"
    ).fetchall()
    assert rows == [("new", "active"), ("old", "superseded")]


class _FakeEmbedder_consolidation_idempotency:
    async def embed(self, text: str) -> list[float]:
        return [0.1, 0.2, 0.3]


def test_parse_history_entry_happened_at_from_prefix():
    assert (
        _parse_history_entry_happened_at("[2026-03-08 12:00] 用户确认信息")
        == "2026-03-08T12:00:00"
    )
    assert (
        _parse_history_entry_happened_at("[2026-03-08T12:01] 用户确认信息")
        == "2026-03-08T12:01:00"
    )
    assert (
        _parse_history_entry_happened_at("[2026-03-08] 用户确认信息")
        == "2026-03-08T00:00:00"
    )
    assert _parse_history_entry_happened_at("用户确认信息") is None


def test_save_from_consolidation_writes_happened_at(tmp_path):
    store = MemoryStore2(
        tmp_path / "memory2.db", open_database=FakeMemoryStorage().open_database
    )
    memorizer = Memorizer(store, cast(Any, _FakeEmbedder_consolidation_idempotency()))

    async def _run() -> None:
        await memorizer.save_from_consolidation(
            history_entry="[2026-03-08 12:00] 用户确认信息",
            behavior_updates=[],
            source_ref="session@1-10",
            scope_channel="telegram",
            scope_chat_id="123",
        )

    asyncio.run(_run())

    items = store.list_by_type("event")
    assert len(items) == 1
    assert items[0]["happened_at"] == "2026-03-08T12:00:00"


def test_save_from_consolidation_skips_duplicate_source_ref(tmp_path):
    store = MemoryStore2(
        tmp_path / "memory2.db", open_database=FakeMemoryStorage().open_database
    )
    memorizer = Memorizer(store, cast(Any, _FakeEmbedder_consolidation_idempotency()))

    async def _run() -> None:
        await memorizer.save_from_consolidation(
            history_entry="[2026-03-08 12:00] second with different text",
            behavior_updates=[],
            source_ref="session@1-10",
            scope_channel="telegram",
            scope_chat_id="123",
        )
        await memorizer.save_from_consolidation(
            history_entry="[2026-03-08 12:00] first",
            behavior_updates=[],
            source_ref="session@1-10",
            scope_channel="telegram",
            scope_chat_id="123",
        )

    asyncio.run(_run())

    items = store.list_by_type("event")
    assert len(items) == 1
    assert items[0]["reinforcement"] == 1


class _FakeEmbedder_event_semantic_dedup:
    def __init__(self, mapping: dict[str, list[float]]) -> None:
        self._mapping = mapping

    async def embed(self, text: str) -> list[float]:
        return list(self._mapping[text])


def test_near_duplicate_event_not_saved_again(tmp_path):
    store = MemoryStore2(
        tmp_path / "memory2.db", open_database=FakeMemoryStorage().open_database
    )
    embedder = _FakeEmbedder_event_semantic_dedup(
        {
            "用户把仓库脱敏后公开发布": [1.0, 0.0],
            "用户公开了脱敏后的仓库": [0.99, 0.01],
        }
    )
    memorizer = Memorizer(store, cast(Any, embedder))

    async def _run() -> None:
        await memorizer.save_from_consolidation(
            history_entry="用户把仓库脱敏后公开发布",
            behavior_updates=[],
            source_ref="session@1-10#0",
            scope_channel="telegram",
            scope_chat_id="1",
        )
        await memorizer.save_from_consolidation(
            history_entry="用户公开了脱敏后的仓库",
            behavior_updates=[],
            source_ref="session@1-10#1",
            scope_channel="telegram",
            scope_chat_id="1",
        )

    asyncio.run(_run())

    items = store.list_by_type("event")
    assert len(items) == 1


def test_distinct_event_saves_normally(tmp_path):
    store = MemoryStore2(
        tmp_path / "memory2.db", open_database=FakeMemoryStorage().open_database
    )
    embedder = _FakeEmbedder_event_semantic_dedup(
        {
            "用户把仓库脱敏后公开发布": [1.0, 0.0],
            "用户买了一个新键盘": [0.0, 1.0],
        }
    )
    memorizer = Memorizer(store, cast(Any, embedder))

    async def _run() -> None:
        await memorizer.save_from_consolidation(
            history_entry="用户把仓库脱敏后公开发布",
            behavior_updates=[],
            source_ref="session@1-10#0",
            scope_channel="telegram",
            scope_chat_id="1",
        )
        await memorizer.save_from_consolidation(
            history_entry="用户买了一个新键盘",
            behavior_updates=[],
            source_ref="session@1-10#1",
            scope_channel="telegram",
            scope_chat_id="1",
        )

    asyncio.run(_run())

    items = store.list_by_type("event")
    assert len(items) == 2


def test_reinforcement_incremented_on_dedup(tmp_path):
    store = MemoryStore2(
        tmp_path / "memory2.db", open_database=FakeMemoryStorage().open_database
    )
    embedder = _FakeEmbedder_event_semantic_dedup(
        {
            "用户把仓库脱敏后公开发布": [1.0, 0.0],
            "用户公开了脱敏后的仓库": [0.99, 0.01],
        }
    )
    memorizer = Memorizer(store, cast(Any, embedder))

    async def _run() -> None:
        await memorizer.save_from_consolidation(
            history_entry="用户把仓库脱敏后公开发布",
            behavior_updates=[],
            source_ref="session@1-10#0",
            scope_channel="telegram",
            scope_chat_id="1",
        )
        await memorizer.save_from_consolidation(
            history_entry="用户公开了脱敏后的仓库",
            behavior_updates=[],
            source_ref="session@1-10#1",
            scope_channel="telegram",
            scope_chat_id="1",
        )

    asyncio.run(_run())

    items = store.list_by_type("event")
    assert items[0]["reinforcement"] == 2


def test_emotional_weight_merged_on_event_dedup(tmp_path):
    store = MemoryStore2(
        tmp_path / "memory2.db", open_database=FakeMemoryStorage().open_database
    )
    embedder = _FakeEmbedder_event_semantic_dedup(
        {
            "用户把仓库脱敏后公开发布": [1.0, 0.0],
            "用户公开了脱敏后的仓库": [0.99, 0.01],
        }
    )
    memorizer = Memorizer(store, cast(Any, embedder))

    async def _run() -> None:
        await memorizer.save_from_consolidation(
            history_entry="用户把仓库脱敏后公开发布",
            behavior_updates=[],
            source_ref="session@1-10#0",
            scope_channel="telegram",
            scope_chat_id="1",
            emotional_weight=0,
        )
        await memorizer.save_from_consolidation(
            history_entry="用户公开了脱敏后的仓库",
            behavior_updates=[],
            source_ref="session@1-10#1",
            scope_channel="telegram",
            scope_chat_id="1",
            emotional_weight=8,
        )

    asyncio.run(_run())

    items = store.list_by_type("event")
    assert items[0]["emotional_weight"] == 8


def test_dedup_window_is_7_days(tmp_path):
    store = MemoryStore2(
        tmp_path / "memory2.db", open_database=FakeMemoryStorage().open_database
    )
    embedder = _FakeEmbedder_event_semantic_dedup(
        {
            "用户把仓库脱敏后公开发布": [1.0, 0.0],
            "用户公开了脱敏后的仓库": [0.99, 0.01],
        }
    )
    memorizer = Memorizer(store, cast(Any, embedder))

    async def _run() -> None:
        await memorizer.save_from_consolidation(
            history_entry="用户把仓库脱敏后公开发布",
            behavior_updates=[],
            source_ref="session@1-10#0",
            scope_channel="telegram",
            scope_chat_id="1",
        )

    asyncio.run(_run())

    old_created_at = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat()
    store._db.execute(
        "UPDATE memory_items SET created_at=?, updated_at=? WHERE memory_type='event'",
        (old_created_at, old_created_at),
    )
    store._db.commit()

    async def _run_again() -> None:
        await memorizer.save_from_consolidation(
            history_entry="用户公开了脱敏后的仓库",
            behavior_updates=[],
            source_ref="session@1-10#1",
            scope_channel="telegram",
            scope_chat_id="1",
        )

    asyncio.run(_run_again())

    items = store.list_by_type("event")
    assert len(items) == 2


class _FakeEmbedder_dedup_baseline:
    def __init__(self, mapping: dict[str, list[float]]) -> None:
        self._mapping = mapping

    async def embed(self, text: str) -> list[float]:
        return list(self._mapping.get(text, [0.0, 0.0, 0.0]))


def test_baseline_exact_hash_prevents_double_write(tmp_path):
    """[PASS] content_hash 去重：完全相同的 summary 写两次，DB 只有一条，reinforcement=2。"""
    store = MemoryStore2(
        tmp_path / "m.db", open_database=FakeMemoryStorage().open_database
    )
    embedder = _FakeEmbedder_dedup_baseline({"查 Steam 必须用 steam MCP": [1.0, 0.0]})
    memorizer = Memorizer(store, cast(Any, embedder))

    async def _run():
        await memorizer.save_item(
            summary="查 Steam 必须用 steam MCP",
            memory_type="procedure",
            extra={},
            source_ref="turn1",
        )
        await memorizer.save_item(
            summary="查 Steam 必须用 steam MCP",
            memory_type="procedure",
            extra={},
            source_ref="turn2",
        )

    asyncio.run(_run())

    items = store.list_by_type("procedure")
    assert len(items) == 1, "完全相同内容不应重复写入"
    assert items[0]["reinforcement"] == 2, "重复写入应增加 reinforcement"


class _StaticEmbedder_post_response_worker:
    def __init__(self, mapping: dict[str, list[float]]):
        self._mapping = mapping

    async def embed(self, text: str) -> list[float]:
        return list(self._mapping.get(text, [0.0, 0.0]))


def test_merge_item_should_keep_procedure_metadata_consistent():
    embedder = _StaticEmbedder_post_response_worker(
        {
            "查 Steam 必须先用 steam_mcp，不能直接使用 web_search": [1.0, 0.0],
            "合并后的 Steam 查询规则：先用 steam_mcp，再补充区服确认": [0.9, 0.1],
        }
    )
    store = MemoryStore2(":memory:", open_database=FakeMemoryStorage().open_database)
    memorizer = Memorizer(store, cast(Any, embedder))

    row_ref = store.upsert_item(
        memory_type="procedure",
        summary="查 Steam 必须先用 steam_mcp，不能直接使用 web_search",
        embedding=[1.0, 0.0],
        extra={
            "tool_requirement": "steam_mcp",
            "steps": [],
            "rule_schema": {
                "required_tools": ["steam_mcp"],
                "forbidden_tools": ["web_search"],
                "mentioned_tools": ["steam_mcp", "web_search"],
            },
        },
    )
    item_id = row_ref.split(":", 1)[1]

    asyncio.run(
        memorizer.merge_item(
            item_id,
            "合并后的 Steam 查询规则：先用 steam_mcp，再补充区服确认",
        )
    )

    row = store._db.execute(
        "SELECT summary, extra_json FROM memory_items WHERE id=?",
        (item_id,),
    ).fetchone()
    assert row is not None
    summary, extra_json = row
    assert "补充区服确认" in summary
    assert extra_json is not None

    import json

    extra = json.loads(extra_json)
    assert extra["tool_requirement"] == "steam_mcp"
    assert "区服确认" in str(extra), "merge 后的 extra_json 应与新摘要保持一致"


def test_merge_item_should_refresh_trigger_tags_for_procedure():
    embedder = _StaticEmbedder_post_response_worker(
        {
            "查 Steam 必须直接使用 web_search": [1.0, 0.0],
            "查 Steam 必须先使用 steam_mcp": [0.9, 0.1],
        }
    )
    store = MemoryStore2(":memory:", open_database=FakeMemoryStorage().open_database)
    memorizer = Memorizer(store, cast(Any, embedder))

    row_ref = store.upsert_item(
        memory_type="procedure",
        summary="查 Steam 必须直接使用 web_search",
        embedding=[1.0, 0.0],
        extra={
            "tool_requirement": "web_search",
            "steps": [],
            "rule_schema": {
                "required_tools": ["web_search"],
                "forbidden_tools": [],
                "mentioned_tools": ["web_search"],
            },
            "trigger_tags": {
                "tools": ["web_search"],
                "skills": [],
                "keywords": ["web_search"],
                "scope": "tool_triggered",
            },
        },
    )
    item_id = row_ref.split(":", 1)[1]

    asyncio.run(
        memorizer.merge_item(
            item_id,
            "查 Steam 必须先使用 steam_mcp",
        )
    )

    row = store._db.execute(
        "SELECT extra_json FROM memory_items WHERE id=?",
        (item_id,),
    ).fetchone()
    assert row is not None and row[0] is not None

    import json

    extra = json.loads(row[0])
    tags = extra.get("trigger_tags") or {}
    assert "web_search" not in (tags.get("keywords") or []), "merge 后不应保留旧关键词"


def test_save_item_with_supersede_does_not_cross_role_scope():
    embedder = _StaticEmbedder_post_response_worker(
        {
            "Mira 视角：用户偏好中文回复": [1.0, 0.0],
            "Atlas 视角：用户偏好中文回复": [1.0, 0.0],
            "Mira 视角：用户更偏好简洁中文回复": [1.0, 0.0],
        }
    )
    store = MemoryStore2(":memory:", open_database=FakeMemoryStorage().open_database)
    memorizer = Memorizer(store, cast(Any, embedder))

    asyncio.run(
        memorizer.save_item_with_supersede(
            summary="Mira 视角：用户偏好中文回复",
            memory_type="preference",
            extra={"role_id": "mira", "memory_domain": "relationship"},
            source_ref="role:mira:seed",
        )
    )
    asyncio.run(
        memorizer.save_item_with_supersede(
            summary="Atlas 视角：用户偏好中文回复",
            memory_type="preference",
            extra={"role_id": "atlas", "memory_domain": "relationship"},
            source_ref="role:atlas:seed",
        )
    )
    asyncio.run(
        memorizer.save_item_with_supersede(
            summary="Mira 视角：用户更偏好简洁中文回复",
            memory_type="preference",
            extra={"role_id": "mira", "memory_domain": "relationship"},
            source_ref="role:mira:update",
            supersede_threshold=0.0,
        )
    )

    rows = store._db.execute(
        "SELECT summary, status, extra_json FROM memory_items WHERE memory_type='preference'"
    ).fetchall()

    import json

    items = []
    for summary, status, extra_json in rows:
        extra = json.loads(extra_json) if extra_json else {}
        items.append((summary, status, extra.get("role_id")))

    assert ("Atlas 视角：用户偏好中文回复", "active", "atlas") in items
    assert ("Mira 视角：用户更偏好简洁中文回复", "active", "mira") in items
    assert ("Mira 视角：用户偏好中文回复", "superseded", "mira") in items
