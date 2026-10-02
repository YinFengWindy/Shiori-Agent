from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, TypeAlias, cast
from unittest.mock import AsyncMock

import pytest
from shiori_sdk.memory.engine import (
    EngineProfile,
    MemoryQuery,
    MemoryQueryFilters,
    MemoryScope,
)
from shiori_sdk.models import ModelProvider as LLMProvider
from shiori_sdk.testing.models import FakeModelResponse as LLMResponse
from shiori_sdk.testing.memory import FakeMemoryStorage

import plugins.default_memory.backend.semantic.retriever as retriever_module
from plugins.default_memory.backend.engine.lifecycle import DefaultMemoryEngine
from plugins.default_memory.backend.semantic.embedder import Embedder
from plugins.default_memory.backend.semantic.retriever import Retriever
from plugins.default_memory.backend.semantic.store import MemoryStore2


async def test_default_memory_engine_retrieve_maps_hits_and_text_block(make_engine):
    retriever = SimpleNamespace(
        retrieve=AsyncMock(
            return_value=[
                {
                    "id": "m1",
                    "summary": "记住用户偏好中文回复",
                    "score": 0.88,
                    "source_ref": "cli:1@seed",
                    "memory_domain": "relationship",
                    "memory_type": "preference",
                    "extra_json": {"origin": "test"},
                }
            ]
        ),
        build_injection_block=lambda items: ("注入块", ["m1"]),
    )
    engine = make_engine(retriever=cast(Any, retriever))

    result = await engine.query(
        MemoryQuery(
            text="中文回复",
            intent="context",
            scope=MemoryScope(role_id="mira", channel="cli", chat_id="1"),
            filters=MemoryQueryFilters(
                kinds=("preference",),
                hints={"require_scope_match": True},
            ),
            limit=3,
        )
    )

    assert result.text_block == "注入块"
    assert len(result.records) == 1
    assert result.records[0].id == "m1"
    assert result.records[0].injected is True
    assert result.records[0].engine_kind == "default"
    assert result.records[0].kind == "preference"
    assert result.records[0].domain == "relationship"
    assert result.trace["profile"] == EngineProfile.RICH_MEMORY_ENGINE.value


async def test_default_memory_engine_retrieve_keeps_raw_items_and_mode_trace(
    make_engine,
):
    retriever = SimpleNamespace(
        retrieve=AsyncMock(
            return_value=[
                {
                    "id": "e1",
                    "summary": "用户昨天提过 FitBit",
                    "score": 0.81,
                    "source_ref": "telegram:1@seed",
                    "memory_type": "event",
                    "extra_json": {"origin": "test"},
                }
            ]
        ),
        build_injection_block=lambda items: ("历史块", ["e1"]),
    )
    engine = make_engine(retriever=cast(Any, retriever))

    result = await engine.query(
        MemoryQuery(
            text="Fitbit 型号",
            intent="context",
            scope=MemoryScope(role_id="mira", session_key="telegram:1"),
            filters=MemoryQueryFilters(
                kinds=("event",),
                hints={"require_scope_match": True},
            ),
            limit=2,
        )
    )

    assert result.text_block == "历史块"
    assert result.trace["intent"] == "context"
    raw = cast(dict[str, object], result.raw)
    raw_items = cast(list[object], raw["items"])
    assert cast(dict[str, object], raw_items[0])["id"] == "e1"
    assert result.records[0].id == "e1"
    assert result.records[0].injected is True


async def test_default_memory_engine_interest_preserves_read_only_effect(make_engine):
    retriever = SimpleNamespace(
        retrieve=AsyncMock(
            return_value=[
                {
                    "id": "p1",
                    "summary": "用户偏好中文回复",
                    "score": 0.8,
                    "source_ref": "telegram:1@seed",
                    "memory_type": "preference",
                    "extra_json": {},
                }
            ]
        ),
        build_injection_block=lambda items: ("", []),
    )
    engine = make_engine(retriever=cast(Any, retriever))

    result = await engine.query(
        MemoryQuery(
            text="中文回复",
            intent="interest",
            effect="read_only",
            scope=MemoryScope(role_id="mira", session_key="telegram:1"),
            limit=2,
        )
    )

    assert result.trace["intent"] == "interest"
    assert result.trace["effect"] == "read_only"
    assert result.records[0].id == "p1"
    retriever.retrieve.assert_awaited_once()


async def test_default_memory_engine_retrieve_falls_back_to_session_scope(make_engine):
    retriever = SimpleNamespace(
        retrieve=AsyncMock(return_value=[]),
        build_injection_block=lambda items: ("", []),
    )
    engine = make_engine(retriever=cast(Any, retriever))

    with pytest.raises(ValueError, match="role_id required for memory scope"):
        await engine.query(
            MemoryQuery(
                text="作用域测试",
                intent="context",
                scope=MemoryScope(session_key="telegram:test_user"),
                filters=MemoryQueryFilters(hints={"require_scope_match": True}),
            )
        )


async def test_default_memory_engine_role_query_excludes_legacy_unscoped_memory(
    tmp_path: Path, make_engine
):
    from plugins.default_memory.backend.semantic.retriever import Retriever

    store = MemoryStore2(
        tmp_path / "memory.db", open_database=FakeMemoryStorage().open_database
    )
    embedder = SimpleNamespace(embed=AsyncMock(return_value=[1.0, 0.0]))
    engine = make_engine(v2_store=store, retriever=Retriever(store, embedder))

    store.upsert_item(
        "profile",
        "legacy 公共记忆：用户常驻上海",
        [1.0, 0.0],
        extra={},
        source_ref="legacy:profile",
    )
    store.upsert_item(
        "profile",
        "角色记忆：Mira 视角下用户常驻上海",
        [1.0, 0.0],
        extra={"role_id": "mira", "memory_domain": "relationship"},
        source_ref="role:mira:profile",
    )

    result = await engine.query(
        MemoryQuery(
            text="用户常驻上海",
            intent="interest",
            scope=MemoryScope(role_id="mira"),
            limit=10,
        )
    )

    summaries = [record.summary for record in result.records]
    assert "角色记忆：Mira 视角下用户常驻上海" in summaries
    assert "legacy 公共记忆：用户常驻上海" not in summaries


async def test_default_memory_engine_isolates_relationship_memory_between_roles(
    tmp_path: Path, make_engine
):
    from plugins.default_memory.backend.semantic.retriever import Retriever

    store = MemoryStore2(
        tmp_path / "memory.db", open_database=FakeMemoryStorage().open_database
    )
    embedder = SimpleNamespace(embed=AsyncMock(return_value=[1.0, 0.0]))
    engine = make_engine(v2_store=store, retriever=Retriever(store, embedder))

    store.upsert_item(
        "preference",
        "Mira 视角：用户偏好中文回复",
        [1.0, 0.0],
        extra={"role_id": "mira", "memory_domain": "relationship"},
        source_ref="role:mira:pref",
    )
    store.upsert_item(
        "preference",
        "Atlas 视角：用户偏好英文回复",
        [1.0, 0.0],
        extra={"role_id": "atlas", "memory_domain": "relationship"},
        source_ref="role:atlas:pref",
    )

    mira_result = await engine.query(
        MemoryQuery(
            text="用户偏好什么语言回复",
            intent="interest",
            scope=MemoryScope(role_id="mira"),
            limit=10,
        )
    )
    atlas_result = await engine.query(
        MemoryQuery(
            text="用户偏好什么语言回复",
            intent="interest",
            scope=MemoryScope(role_id="atlas"),
            limit=10,
        )
    )

    mira_summaries = [record.summary for record in mira_result.records]
    atlas_summaries = [record.summary for record in atlas_result.records]
    assert "Mira 视角：用户偏好中文回复" in mira_summaries
    assert "Atlas 视角：用户偏好英文回复" not in mira_summaries
    assert "Atlas 视角：用户偏好英文回复" in atlas_summaries
    assert "Mira 视角：用户偏好中文回复" not in atlas_summaries


async def test_default_engine_keeps_history_injected_ids(make_engine):
    retriever = SimpleNamespace(
        retrieve=AsyncMock(
            return_value=[
                {
                    "id": "e1",
                    "summary": "用户昨天提过 FitBit",
                    "score": 0.81,
                    "source_ref": "telegram:1@seed",
                    "memory_type": "event",
                    "extra_json": {"origin": "engine"},
                }
            ]
        ),
        build_injection_block=lambda items: (
            "## 【相关历史】\n- 用户昨天提过 FitBit",
            ["e1"],
        ),
    )
    engine = make_engine(retriever=cast(Any, retriever))

    history_result = await engine.query(
        MemoryQuery(
            text="Fitbit 型号",
            intent="context",
            scope=MemoryScope(
                role_id="mira",
                session_key="telegram:1",
                channel="telegram",
                chat_id="1",
            ),
            filters=MemoryQueryFilters(
                kinds=("event",),
                hints={"require_scope_match": True},
            ),
            limit=8,
        )
    )

    assert "用户昨天提过 FitBit" in history_result.text_block
    assert [record.id for record in history_result.records if record.injected] == ["e1"]


async def test_default_memory_engine_query_passes_memory_domains(make_engine):
    retriever = SimpleNamespace(
        retrieve=AsyncMock(return_value=[]),
        build_injection_block=lambda items: ("", []),
    )
    engine = make_engine(retriever=cast(Any, retriever))

    await engine.query(
        MemoryQuery(
            text="角色自我设定",
            intent="context",
            scope=MemoryScope(role_id="mira"),
            filters=MemoryQueryFilters(
                domains=("role_self",),
            ),
        )
    )

    assert retriever.retrieve.await_args.kwargs["memory_domains"] == ["role_self"]


async def test_default_memory_engine_filters_unauthorized_shared_query(
    tmp_path: Path, make_engine
):
    retriever = SimpleNamespace(
        retrieve=AsyncMock(return_value=[]),
        build_injection_block=lambda items: ("", []),
    )
    engine = make_engine(retriever=cast(Any, retriever))
    engine._workspace = tmp_path

    result = await engine.query(
        MemoryQuery(
            text="共享资料",
            intent="context",
            scope=MemoryScope(role_id="mira"),
            filters=MemoryQueryFilters(domains=("shared",)),
        )
    )

    retriever.retrieve.assert_not_awaited()
    assert result.records == []
    assert result.raw == {"items": []}
    assert result.trace["denied_reason"] == "memory_domain_unauthorized"


async def test_default_memory_engine_timeline_query_honors_role_scope_and_domain_filters(
    tmp_path: Path, make_engine
):
    store = MemoryStore2(
        tmp_path / "memory2.db", open_database=FakeMemoryStorage().open_database
    )
    engine = make_engine(retriever=cast(Any, SimpleNamespace()))
    engine._v2_store = store
    try:
        store.upsert_item(
            memory_type="event",
            summary="[2026-04-25 09:00] Mira room-1",
            embedding=[1.0, 0.0],
            source_ref="tg:1",
            extra={
                "role_id": "mira",
                "memory_domain": "relationship",
                "scope_channel": "telegram",
                "scope_chat_id": "room-1",
            },
            happened_at="2026-04-25T09:00:00",
        )
        store.upsert_item(
            memory_type="event",
            summary="[2026-04-25 10:00] Mira room-2",
            embedding=[1.0, 0.0],
            source_ref="tg:2",
            extra={
                "role_id": "mira",
                "memory_domain": "relationship",
                "scope_channel": "telegram",
                "scope_chat_id": "room-2",
            },
            happened_at="2026-04-25T10:00:00",
        )
        store.upsert_item(
            memory_type="event",
            summary="[2026-04-25 11:00] Atlas room-1",
            embedding=[1.0, 0.0],
            source_ref="tg:3",
            extra={
                "role_id": "atlas",
                "memory_domain": "relationship",
                "scope_channel": "telegram",
                "scope_chat_id": "room-1",
            },
            happened_at="2026-04-25T11:00:00",
        )

        result = await engine.query(
            MemoryQuery(
                text="今天我做了什么",
                intent="timeline",
                scope=MemoryScope(
                    role_id="mira",
                    session_key="telegram:room-1",
                    channel="telegram",
                    chat_id="room-1",
                ),
                filters=MemoryQueryFilters(
                    domains=("relationship",),
                    time_start=datetime.fromisoformat("2026-04-25T00:00:00+08:00"),
                    time_end=datetime.fromisoformat("2026-04-26T00:00:00+08:00"),
                ),
                limit=10,
            )
        )

        assert [record.summary for record in result.records] == [
            "[2026-04-25 09:00] Mira room-1"
        ]
    finally:
        store.close()


async def test_default_memory_engine_timeline_query_rejects_unauthorized_shared_domain(
    tmp_path: Path, make_engine
):
    store = MemoryStore2(
        tmp_path / "memory2.db", open_database=FakeMemoryStorage().open_database
    )
    engine = make_engine(retriever=cast(Any, SimpleNamespace()))
    engine._workspace = tmp_path
    engine._v2_store = store
    try:
        result = await engine.query(
            MemoryQuery(
                text="共享时间线",
                intent="timeline",
                scope=MemoryScope(role_id="mira"),
                filters=MemoryQueryFilters(
                    domains=("shared",),
                    time_start=datetime.fromisoformat("2026-04-25T00:00:00+08:00"),
                    time_end=datetime.fromisoformat("2026-04-26T00:00:00+08:00"),
                ),
            )
        )

        assert result.records == []
        assert result.raw == {"items": []}
        assert result.trace["denied_reason"] == "memory_domain_unauthorized"
    finally:
        store.close()


async def test_default_memory_engine_timeline_query_requires_role_scope(
    tmp_path: Path, make_engine
):
    store = MemoryStore2(
        tmp_path / "memory2.db", open_database=FakeMemoryStorage().open_database
    )
    engine = make_engine(retriever=cast(Any, SimpleNamespace()))
    engine._v2_store = store
    try:
        with pytest.raises(ValueError, match="role_id required"):
            await engine.query(
                MemoryQuery(
                    text="今天我做了什么",
                    intent="timeline",
                    scope=MemoryScope(),
                    filters=MemoryQueryFilters(
                        time_start=datetime.fromisoformat("2026-04-25T00:00:00+08:00"),
                        time_end=datetime.fromisoformat("2026-04-26T00:00:00+08:00"),
                    ),
                    limit=10,
                )
            )
    finally:
        store.close()


async def test_retrieval_hypothesis_requests_auxiliary_reasoning(monkeypatch):
    provider = AsyncMock()
    provider.chat.return_value = LLMResponse(content="你喜欢拿铁")
    engine = DefaultMemoryEngine.__new__(DefaultMemoryEngine)
    monkeypatch.setattr(engine, "_light_provider", provider, raising=False)
    monkeypatch.setattr(engine, "_light_model", "retrieval-model", raising=False)

    result = await engine._gen_hypothesis("我喜欢喝什么？", "preference")

    assert result == "你喜欢拿铁"
    request = provider.chat.await_args.kwargs
    assert request["call_purpose"] == "auxiliary"
    assert request["max_tokens"] == 80


_MemoryHit_query_integration: TypeAlias = dict[str, object]


def _recall_engine_query_integration(
    store: object, embedder: object, provider: object
) -> DefaultMemoryEngine:
    retriever = Retriever(cast(MemoryStore2, store), cast(Embedder, embedder))
    facade = DefaultMemoryEngine.__new__(DefaultMemoryEngine)
    facade._config = None
    facade._workspace = Path(".")
    facade._provider = cast(LLMProvider, provider)
    facade._light_provider = cast(LLMProvider, provider)
    facade._light_model = "test-model"
    facade._v1_store = None
    facade._v2_store = store
    facade._embedder = embedder
    facade._memorizer = None
    facade._retriever = retriever
    facade._tagger = None
    facade._post_response_worker = None
    facade._event_bus = None
    facade._consolidation = None
    spec = facade.tool_profile().recall
    assert spec is not None
    return facade


class _FakeProvider_query_integration:
    chat: AsyncMock

    def __init__(self, content: str = "") -> None:
        self.chat = AsyncMock(return_value=LLMResponse(content=content))


class _FailingEmbedder_query_integration:
    async def embed(self, text: str) -> list[float]:
        raise RuntimeError(f"embed failed: {text}")


class _HangingEmbedder_query_integration:
    async def embed(self, text: str) -> list[float]:
        await asyncio.Event().wait()
        return []


class _StaticEmbedder_query_integration:
    async def embed(self, text: str) -> list[float]:
        return [1.0, 0.0]


class _KeywordOnlyStore_query_integration:
    def __init__(self) -> None:
        self.vector_search_called = False

    def vector_search(
        self, *_args: object, **_kwargs: object
    ) -> list[_MemoryHit_query_integration]:
        self.vector_search_called = True
        return []

    def keyword_search_summary(
        self,
        terms: list[str],
        memory_types: list[str] | None = None,
        limit: int = 20,
        **_kwargs: object,
    ) -> list[_MemoryHit_query_integration]:
        assert "支付" in terms
        assert memory_types is None
        assert limit == 30
        return [
            {
                "id": "mem:1",
                "memory_type": "event",
                "summary": "用户处理过支付相关问题",
                "source_ref": "tg:1:2",
                "happened_at": "2026-01-01T00:00:00+00:00",
                "keyword_score": 1.0,
            }
        ]


class _TimelineStore_query_integration:
    def __init__(self) -> None:
        self.vector_search_called = False
        self.keyword_search_called = False
        self.time_start: datetime | None = None
        self.time_end: datetime | None = None

    def vector_search(
        self, *_args: object, **_kwargs: object
    ) -> list[_MemoryHit_query_integration]:
        self.vector_search_called = True
        return []

    def keyword_search_summary(
        self, *_args: object, **_kwargs: object
    ) -> list[_MemoryHit_query_integration]:
        self.keyword_search_called = True
        return []

    def list_events_by_time_range(
        self,
        time_start: datetime,
        time_end: datetime,
        limit: int = 200,
        **_kwargs: object,
    ) -> list[_MemoryHit_query_integration]:
        self.time_start = time_start
        self.time_end = time_end
        assert limit == 80
        hits: list[_MemoryHit_query_integration] = [
            {
                "id": "e1",
                "memory_type": "event",
                "summary": "[2026-04-25 09:00] 用户调试缓存",
                "source_ref": "tg:1",
                "happened_at": "2026-04-25T09:00:00",
            },
            {
                "id": "e2",
                "memory_type": "event",
                "summary": "[2026-04-25 11:00] 用户讨论 DeepSeek",
                "source_ref": "tg:2",
                "happened_at": "2026-04-25T11:00:00",
            },
        ]
        return hits[:limit]


class _TimedSemanticStore_query_integration:
    def __init__(self) -> None:
        self.vector_kwargs: list[dict[str, object]] = []
        self.vector_batch_kwargs: list[dict[str, object]] = []
        self.vector_batch_vec_count = 0
        self.keyword_kwargs: list[dict[str, object]] = []

    def vector_search(
        self, *_args: object, **kwargs: object
    ) -> list[_MemoryHit_query_integration]:
        self.vector_kwargs.append(kwargs)
        raise AssertionError("带 time_filter 的 semantic 模式应复用 batch 候选")

    def vector_search_batch(
        self, query_vecs: list[list[float]], **kwargs: object
    ) -> list[list[_MemoryHit_query_integration]]:
        self.vector_batch_kwargs.append(kwargs)
        self.vector_batch_vec_count = len(query_vecs)
        return [
            [
                {
                    "id": "deepseek",
                    "memory_type": "event",
                    "summary": "[2026-04-25 03:19] 用户调试 DeepSeek 缓存命中率",
                    "source_ref": "tg:1",
                    "happened_at": "2026-04-25T03:19:00",
                    "score": 0.9,
                }
            ]
            for _query_vec in query_vecs
        ]

    def keyword_search_summary(
        self, _terms: list[str], **kwargs: object
    ) -> list[_MemoryHit_query_integration]:
        self.keyword_kwargs.append(kwargs)
        return []

    def list_events_by_time_range(
        self, *_args: object, **_kwargs: object
    ) -> list[_MemoryHit_query_integration]:
        raise AssertionError("semantic 模式不应直接走 grep 列表")


@pytest.mark.asyncio
async def test_recall_memory_timeline_intent_lists_events_without_embedding() -> None:
    store = _TimelineStore_query_integration()
    provider = _FakeProvider_query_integration()
    engine = _recall_engine_query_integration(
        store, _FailingEmbedder_query_integration(), provider
    )

    result = await engine.query(
        MemoryQuery(
            text="今天我都做了什么",
            intent="timeline",
            scope=MemoryScope(role_id="mira"),
            filters=MemoryQueryFilters(
                time_start=datetime(2026, 4, 25), time_end=datetime(2026, 4, 26)
            ),
            limit=80,
        )
    )
    assert [record.id for record in result.records] == ["e1", "e2"]
    assert store.vector_search_called is False
    assert store.keyword_search_called is False
    provider.chat.assert_not_called()
    assert store.time_start is not None
    assert store.time_end is not None


@pytest.mark.asyncio
async def test_recall_memory_answer_intent_passes_time_range_to_searches() -> None:
    store = _TimedSemanticStore_query_integration()
    provider = _FakeProvider_query_integration("用户讨论 DeepSeek 缓存")
    engine = _recall_engine_query_integration(
        store, _StaticEmbedder_query_integration(), provider
    )

    result = await engine.query(
        MemoryQuery(
            text="DeepSeek 缓存命中率",
            intent="answer",
            scope=MemoryScope(role_id="mira"),
            filters=MemoryQueryFilters(
                time_start=datetime(2026, 4, 25), time_end=datetime(2026, 4, 26)
            ),
        )
    )
    assert result.records[0].id == "deepseek"
    assert store.vector_kwargs == []
    assert store.vector_batch_kwargs
    assert store.vector_batch_vec_count == 2
    assert store.keyword_kwargs
    assert store.vector_batch_kwargs[0]["memory_types"] is None
    assert store.vector_batch_kwargs[0]["time_start"] is not None
    assert store.vector_batch_kwargs[0]["time_end"] is not None
    assert store.keyword_kwargs[0]["memory_types"] is None
    assert store.keyword_kwargs[0]["time_start"] is not None
    assert store.keyword_kwargs[0]["time_end"] is not None


@pytest.mark.asyncio
async def test_recall_memory_falls_back_to_keyword_when_query_embed_fails() -> None:
    store = _KeywordOnlyStore_query_integration()
    provider = _FakeProvider_query_integration("用户处理过支付相关问题")
    engine = _recall_engine_query_integration(
        store, _FailingEmbedder_query_integration(), provider
    )

    result = await engine.query(
        MemoryQuery(text="phase 支付", scope=MemoryScope(role_id="mira"))
    )
    assert len(result.records) == 1
    assert result.records[0].id == "mem:1"
    assert result.records[0].evidence[0].source_ref == "tg:1:2"
    assert store.vector_search_called is False


@pytest.mark.asyncio
async def test_recall_memory_falls_back_to_keyword_when_query_embed_hangs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(retriever_module, "_EMBED_TIMEOUT_S", 0.01)
    store = _KeywordOnlyStore_query_integration()
    provider = _FakeProvider_query_integration("用户处理过支付相关问题")
    engine = _recall_engine_query_integration(
        store, _HangingEmbedder_query_integration(), provider
    )

    result = await asyncio.wait_for(
        engine.query(MemoryQuery(text="phase 支付", scope=MemoryScope(role_id="mira"))),
        timeout=0.5,
    )
    assert len(result.records) == 1
    assert result.records[0].id == "mem:1"
    assert store.vector_search_called is False
