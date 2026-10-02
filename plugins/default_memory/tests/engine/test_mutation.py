from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from shiori_sdk.memory.engine import (
    MemoryIngestRequest,
    MemoryMutation,
    MemoryScope,
)
from shiori_sdk.testing.memory import FakeMemoryRoles

from plugins.default_memory.backend.semantic.memorizer import Memorizer


async def test_default_memory_engine_ingest_delegates_to_post_worker(make_engine):
    worker = SimpleNamespace(run=AsyncMock())
    engine = make_engine(
        retriever=cast(Any, SimpleNamespace()),
        post_response_worker=cast(Any, worker),
    )

    result = await engine.ingest(
        MemoryIngestRequest(
            content={
                "user_message": "以后用中文",
                "assistant_response": "好的",
                "tool_chain": [{"text": "memo", "calls": []}],
            },
            source_kind="conversation_turn",
            scope=MemoryScope(role_id="mira", session_key="role:mira"),
        )
    )

    assert result.accepted is True
    assert result.raw["engine"] == "default"
    worker.run.assert_awaited_once()


async def test_default_memory_engine_remember_uses_memorizer(make_engine):
    memorizer = SimpleNamespace(
        save_item_with_supersede=AsyncMock(return_value="new:memu-1")
    )
    engine = make_engine(
        retriever=cast(Any, SimpleNamespace()),
        memorizer=cast(Any, memorizer),
    )

    result = await engine.mutate(
        MemoryMutation(
            kind="remember",
            summary="以后用中文回复",
            memory_kind="preference",
            scope=MemoryScope(
                role_id="mira",
                session_key="role:mira",
                channel="desktop",
                chat_id="role:mira",
            ),
        )
    )

    assert result.item_id == "memu-1"
    assert result.status == "new"
    memorizer.save_item_with_supersede.assert_awaited_once()
    assert (
        memorizer.save_item_with_supersede.await_args.kwargs["extra"]["memory_domain"]
        == "relationship"
    )


async def test_default_memory_engine_remember_forwards_happened_at(make_engine):
    memorizer = SimpleNamespace(
        save_item_with_supersede=AsyncMock(return_value="new:event-1")
    )
    engine = make_engine(
        retriever=cast(Any, SimpleNamespace()),
        memorizer=cast(Any, memorizer),
    )

    await engine.mutate(
        MemoryMutation(
            kind="remember",
            summary="下午一起整理了报告",
            memory_kind="event",
            scope=MemoryScope(role_id="mira"),
            happened_at="2026-07-23T12:00:00Z",
        )
    )

    assert (
        memorizer.save_item_with_supersede.await_args.kwargs["happened_at"]
        == "2026-07-23T12:00:00Z"
    )


async def test_default_memory_engine_remember_keeps_explicit_memory_domain(make_engine):
    memorizer = SimpleNamespace(
        save_item_with_supersede=AsyncMock(return_value="new:memu-1")
    )
    engine = make_engine(
        retriever=cast(Any, SimpleNamespace()),
        memorizer=cast(Any, memorizer),
    )

    _ = await engine.mutate(
        MemoryMutation(
            kind="remember",
            summary="角色坚持诚实表达",
            memory_kind="identity",
            memory_domain="role_self",
            scope=MemoryScope(role_id="mira"),
        )
    )

    assert (
        memorizer.save_item_with_supersede.await_args.kwargs["extra"]["memory_domain"]
        == "role_self"
    )


async def test_default_memory_engine_remember_role_scope_persists_role_id(make_engine):
    memorizer = SimpleNamespace(
        save_item_with_supersede=AsyncMock(return_value="new:memu-1")
    )
    engine = make_engine(
        retriever=cast(Any, SimpleNamespace()),
        memorizer=cast(Any, memorizer),
    )

    _ = await engine.mutate(
        MemoryMutation(
            kind="remember",
            summary="角色视角下用户偏好中文回复",
            memory_kind="preference",
            scope=MemoryScope(role_id="mira"),
        )
    )

    assert (
        memorizer.save_item_with_supersede.await_args.kwargs["extra"]["role_id"]
        == "mira"
    )


async def test_default_memory_engine_rejects_unauthorized_shared_write(
    tmp_path: Path, make_engine
):
    memorizer = SimpleNamespace(
        save_item_with_supersede=AsyncMock(return_value="new:memu-1")
    )
    engine = make_engine(
        retriever=cast(Any, SimpleNamespace()),
        memorizer=cast(Any, memorizer),
    )
    engine._workspace = tmp_path

    with pytest.raises(ValueError, match="memory_domain 未授权: shared"):
        await engine.mutate(
            MemoryMutation(
                kind="remember",
                summary="共享用户硬事实",
                memory_kind="profile",
                memory_domain="shared",
                scope=MemoryScope(role_id="mira"),
            )
        )


async def test_default_memory_engine_allows_authorized_shared_write(
    tmp_path: Path, make_engine
):

    memorizer = SimpleNamespace(
        save_item_with_supersede=AsyncMock(return_value="new:memu-1")
    )
    engine = make_engine(
        retriever=cast(Any, SimpleNamespace()),
        memorizer=cast(Any, memorizer),
    )
    engine._workspace = tmp_path
    engine._roles = FakeMemoryRoles(("mira",), ("mira",))

    _ = await engine.mutate(
        MemoryMutation(
            kind="remember",
            summary="共享用户硬事实",
            memory_kind="profile",
            memory_domain="shared",
            scope=MemoryScope(role_id="mira"),
        )
    )

    assert (
        memorizer.save_item_with_supersede.await_args.kwargs["extra"]["memory_domain"]
        == "shared"
    )


async def test_default_memory_engine_forget_filters_to_matching_role_and_scope(
    tmp_path: Path, make_engine, make_store
):
    store = make_store(tmp_path / "memory2.db")
    engine = make_engine(retriever=cast(Any, SimpleNamespace()))
    engine._v2_store = store
    try:
        same_scope = store.upsert_item(
            memory_type="event",
            summary="[2026-04-25 09:00] Mira room-1",
            embedding=[1.0, 0.0],
            source_ref="tg:1",
            extra={
                "role_id": "mira",
                "scope_channel": "telegram",
                "scope_chat_id": "room-1",
            },
            happened_at="2026-04-25T09:00:00",
        ).split(":", 1)[1]
        other_scope = store.upsert_item(
            memory_type="event",
            summary="[2026-04-25 10:00] Mira room-2",
            embedding=[1.0, 0.0],
            source_ref="tg:2",
            extra={
                "role_id": "mira",
                "scope_channel": "telegram",
                "scope_chat_id": "room-2",
            },
            happened_at="2026-04-25T10:00:00",
        ).split(":", 1)[1]
        other_role = store.upsert_item(
            memory_type="event",
            summary="[2026-04-25 11:00] Atlas room-1",
            embedding=[1.0, 0.0],
            source_ref="tg:3",
            extra={
                "role_id": "atlas",
                "scope_channel": "telegram",
                "scope_chat_id": "room-1",
            },
            happened_at="2026-04-25T11:00:00",
        ).split(":", 1)[1]

        result = await engine.mutate(
            MemoryMutation(
                kind="forget",
                ids=(same_scope, other_scope, other_role),
                scope=MemoryScope(
                    role_id="mira",
                    session_key="telegram:room-1",
                    channel="telegram",
                    chat_id="room-1",
                ),
            )
        )

        assert result.affected_ids == [same_scope]
        assert set(result.missing_ids) == {other_scope, other_role}
        assert store.get_items_by_ids([same_scope])[0]["status"] == "superseded"
        assert store.get_items_by_ids([other_scope])[0]["status"] == "active"
        assert store.get_items_by_ids([other_role])[0]["status"] == "active"
    finally:
        store.close()


async def test_default_memory_engine_remember_merged_keeps_target_id_alive(make_engine):
    memorizer = SimpleNamespace(
        save_item_with_supersede=AsyncMock(return_value="merged:memu-1")
    )
    engine = make_engine(
        retriever=cast(Any, SimpleNamespace()),
        memorizer=cast(Any, memorizer),
    )

    result = await engine.mutate(
        MemoryMutation(
            kind="remember",
            summary="以后用中文回复",
            memory_kind="preference",
            scope=MemoryScope(
                role_id="mira",
                session_key="role:mira",
                channel="desktop",
                chat_id="role:mira",
            ),
        )
    )

    assert result.item_id == "memu-1"
    assert result.status == "merged"
    assert result.affected_ids == []


async def test_default_memory_engine_ingest_accepts_conversation_batch_messages(
    make_engine,
):
    worker = SimpleNamespace(run=AsyncMock())
    engine = make_engine(
        retriever=cast(Any, SimpleNamespace()),
        post_response_worker=cast(Any, worker),
    )

    result = await engine.ingest(
        MemoryIngestRequest(
            content=[
                {"role": "user", "content": "以后用中文"},
                {
                    "role": "assistant",
                    "content": "好的",
                    "tool_chain": [{"text": "memo", "calls": []}],
                },
            ],
            source_kind="conversation_batch",
            scope=MemoryScope(role_id="mira", session_key="role:mira"),
        )
    )

    assert result.accepted is True
    kwargs = worker.run.await_args.kwargs
    assert kwargs["user_msg"] == "以后用中文"
    assert kwargs["agent_response"] == "好的"
    assert kwargs["tool_chain"] == [{"text": "memo", "calls": []}]
    assert kwargs["session_key"] == "role:mira"


async def test_default_memory_engine_ingest_falls_back_to_post_response_source_ref(
    make_engine,
):
    worker = SimpleNamespace(run=AsyncMock())
    engine = make_engine(
        retriever=cast(Any, SimpleNamespace()),
        post_response_worker=cast(Any, worker),
    )

    result = await engine.ingest(
        MemoryIngestRequest(
            content={
                "user_message": "以后用中文",
                "assistant_response": "好的",
            },
            source_kind="conversation_turn",
            scope=MemoryScope(role_id="mira", session_key="role:mira"),
        )
    )

    assert result.accepted is True
    kwargs = worker.run.await_args.kwargs
    assert kwargs["source_ref"] == "role:mira@post_response"
    assert kwargs["session_key"] == "role:mira"


async def test_default_memory_engine_ingest_rejects_unsupported_source_kind(
    make_engine,
):
    worker = SimpleNamespace(run=AsyncMock())
    engine = make_engine(
        retriever=cast(Any, SimpleNamespace()),
        post_response_worker=cast(Any, worker),
    )

    result = await engine.ingest(
        MemoryIngestRequest(
            content="以后用中文",
            source_kind="text",
            scope=MemoryScope(role_id="mira", session_key="role:mira"),
        )
    )

    assert result.accepted is False
    assert result.raw["reason"] == "unsupported_source_kind"
    worker.run.assert_not_awaited()


async def test_default_memory_engine_ingest_rejects_when_worker_missing(make_engine):
    engine = make_engine(
        retriever=cast(Any, SimpleNamespace()),
        post_response_worker=None,
    )

    result = await engine.ingest(
        MemoryIngestRequest(
            content={
                "user_message": "以后用中文",
                "assistant_response": "好的",
            },
            source_kind="conversation_turn",
            scope=MemoryScope(role_id="mira", session_key="role:mira"),
        )
    )

    assert result.accepted is False
    assert result.raw["reason"] == "worker_unavailable"


@pytest.mark.asyncio
async def test_memorize_tool_cover_branches(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, make_engine
):
    memorizer = MagicMock()
    memorizer.save_item_with_supersede = AsyncMock(return_value="new:mem-1")

    class _Tagger:
        async def tag(self, summary: str) -> dict[str, str]:
            assert summary == "记住这条流程"
            return {"scope": "task"}

    tool = make_engine(
        retriever=MagicMock(),
        memorizer=memorizer,
        tagger=cast(Any, _Tagger()),
    )
    result = await tool.mutate(
        MemoryMutation(
            kind="remember",
            scope=MemoryScope(role_id="mira"),
            summary="记住这条流程",
            memory_kind="procedure",
            metadata={"steps": ["先查", "再做"]},
        )
    )

    assert result.item_id == "mem-1"
    assert result.status == "new"
    extra = memorizer.save_item_with_supersede.await_args.kwargs["extra"]
    assert extra["trigger_tags"] == {"scope": "task"}
    assert extra["rule_schema"]["required_tools"] == []
    assert extra["rule_schema"]["forbidden_tools"] == []

    class _BadTagger:
        async def tag(self, summary: str) -> dict[str, str]:
            raise RuntimeError("bad")

    bad = make_engine(
        retriever=MagicMock(),
        memorizer=memorizer,
        tagger=cast(Any, _BadTagger()),
    )
    await bad.mutate(
        MemoryMutation(
            kind="remember",
            scope=MemoryScope(role_id="mira"),
            summary="普通偏好",
            memory_kind="procedure",
        )
    )
    await bad.mutate(
        MemoryMutation(
            kind="remember",
            scope=MemoryScope(role_id="mira"),
            summary="偏好",
            memory_kind="preference",
        )
    )


@pytest.mark.asyncio
async def test_memorize_tool_should_not_create_second_active_procedure_when_incremental_update(
    make_engine,
    make_store,
):
    class _Embedder:
        async def embed(self, text: str) -> list[float]:
            return [1.0, 0.0]

    store = make_store(":memory:")
    memorizer = Memorizer(store, cast(Any, _Embedder()))
    tool = make_engine(
        retriever=MagicMock(),
        memorizer=memorizer,
    )

    await memorizer.save_item(
        summary="查询 Steam 游戏信息时，必须先使用 steam_mcp 工具查询游戏详情，再用 web_search 补充验证价格和评价信息。",
        memory_type="procedure",
        extra={
            "steps": [
                "使用 steam_mcp 工具查询游戏详情",
                "使用 web_search 补充验证价格和评价",
            ],
            "tool_requirement": "steam_mcp",
            "role_id": "mira",
        },
        source_ref="seed",
    )

    await tool.mutate(
        MemoryMutation(
            kind="remember",
            scope=MemoryScope(role_id="mira"),
            summary="查询 Steam 游戏信息时，先判断区服（大陆区/港区/美区），再使用 steam_mcp 工具查询游戏详情。",
            memory_kind="procedure",
            metadata={
                "tool_requirement": "steam_mcp",
                "steps": ["判断目标区服", "使用 steam_mcp 工具查询游戏详情"],
            },
        )
    )

    rows = store._db.execute(
        "SELECT id, summary FROM memory_items WHERE memory_type='procedure' AND status='active'"
    ).fetchall()
    assert len(rows) == 1
    assert "steam_mcp" in rows[0][1]
    assert "区服" in rows[0][1]


@pytest.mark.asyncio
async def test_memorize_tool_should_coerce_language_reply_rule_to_preference(
    make_engine,
):
    memorizer = MagicMock()
    memorizer.save_item_with_supersede = AsyncMock(return_value="new:mem-1")
    tool = make_engine(
        retriever=MagicMock(),
        memorizer=memorizer,
    )

    await tool.mutate(
        MemoryMutation(
            kind="remember",
            scope=MemoryScope(role_id="mira"),
            summary="之后跟我说话只用中文，不要夹杂英文，专有名词也尽量翻译。",
            memory_kind="procedure",
        )
    )

    assert (
        memorizer.save_item_with_supersede.await_args.kwargs["memory_type"]
        == "preference"
    )
