import asyncio
from typing import Any, cast
from unittest.mock import AsyncMock

from core.memory.events import MemoryWritten, TurnIngested
from memory2.memorizer import Memorizer
from memory2.post_response_worker import PostResponseMemoryWorker
from memory2.rule_schema import build_procedure_rule_schema
from memory2.store import MemoryStore2


class _DummyProvider:
    def __init__(self):
        self.calls = 0

    async def chat(self, **kwargs):
        self.calls += 1
        raise AssertionError("provider.chat should not be called in this test")


class _DummyRetriever:
    def __init__(self, results):
        self._results = results
        self.calls = []

    async def retrieve(self, query: str, memory_types=None, **kwargs):
        self.calls.append((query, tuple(memory_types or []), dict(kwargs)))
        return list(self._results)


class _DummyMemorizer:
    def __init__(self, store=None):
        from unittest.mock import AsyncMock, MagicMock

        self.save_item = AsyncMock(return_value="new:testid")
        self.supersede_batch = MagicMock()
        self.merge_item = AsyncMock()
        self._store = store


class _StaticEmbedder:
    def __init__(self, mapping: dict[str, list[float]]):
        self._mapping = mapping

    async def embed(self, text: str) -> list[float]:
        return list(self._mapping.get(text, [0.0, 0.0]))


def test_post_worker_run_only_handles_invalidations_no_implicit_save():
    """per-turn run() 只做 invalidation 处理，不再做隐式 procedure/preference/profile 提取。
    隐式提取已移至 consolidation 窗口期（与 event 提取并行，用主模型处理）。
    """
    from unittest.mock import AsyncMock, MagicMock

    memorizer = _DummyMemorizer()
    retriever = _DummyRetriever([])
    worker = PostResponseMemoryWorker(
        memorizer=cast(Any, memorizer),
        retriever=cast(Any, retriever),
        light_provider=cast(Any, _DummyProvider()),
        light_model="test",
    )
    worker._handle_invalidations = AsyncMock(
        side_effect=lambda *args, **kwargs: args[-1] if args else 0
    )

    asyncio.run(
        worker.run(
            user_msg="你以后多问我一句",
            agent_response="好的",
            tool_chain=[],
            source_ref="test@post_response",
        )
    )

    # run() 不再写入任何隐式记忆
    memorizer.save_item.assert_not_called()
    # 但 invalidation 检查仍然运行
    worker._handle_invalidations.assert_awaited_once()


def test_post_worker_handle_delegates_turn_ingested_event():
    worker = PostResponseMemoryWorker(
        memorizer=cast(Any, _DummyMemorizer()),
        retriever=cast(Any, _DummyRetriever([])),
        light_provider=cast(Any, _DummyProvider()),
        light_model="test",
    )
    worker.run = AsyncMock()

    asyncio.run(
        worker.handle(
            TurnIngested(
                session_key="cli:1",
                channel="cli",
                chat_id="1",
                user_message="以后用中文",
                assistant_response="好的",
                tool_chain=[{"text": "memo", "calls": []}],
                source_ref="cli:1@post_response",
            )
        )
    )

    worker.run.assert_awaited_once_with(
        user_msg="以后用中文",
        agent_response="好的",
        tool_chain=[{"text": "memo", "calls": []}],
        source_ref="cli:1@post_response",
        session_key="cli:1",
        channel="cli",
        chat_id="1",
        role_id="",
    )


def test_build_procedure_rule_schema_prefers_explicit_rule_schema():
    schema = build_procedure_rule_schema(
        "查 Steam 信息时不要直接用 web_search，必须先使用 steam MCP。",
        tool_requirement="steam_mcp",
        rule_schema={
            "required_tools": ["steam_mcp"],
            "forbidden_tools": ["web_search"],
            "mentioned_tools": ["steam", "web_search"],
        },
    )

    assert "web_search" in schema["forbidden_tools"]
    assert schema["required_tools"] == ["steam_mcp"]
    assert "steam" in schema["mentioned_tools"]


def test_build_procedure_rule_schema_fills_missing_slot_from_summary():
    schema = build_procedure_rule_schema(
        "查 Steam 信息时必须先使用 steam MCP，不能直接使用 web_search。",
        rule_schema={"required_tools": ["steam_mcp"]},
    )

    assert schema["required_tools"] == ["steam_mcp"]
    assert schema["forbidden_tools"] == ["web_search"]


def test_build_procedure_rule_schema_infers_constraints_without_explicit_schema():
    schema = build_procedure_rule_schema(
        "查 Steam 信息时不要直接用 web_search，必须先使用 steam MCP。"
    )

    assert "steam_mcp" in schema["required_tools"]
    assert "web_search" in schema["forbidden_tools"]
    assert "steam" in schema["mentioned_tools"]


def test_collect_explicit_memorized_accepts_long_mixed_id():
    worker = PostResponseMemoryWorker(
        memorizer=cast(Any, _DummyMemorizer()),
        retriever=cast(Any, _DummyRetriever([])),
        light_provider=cast(Any, _DummyProvider()),
        light_model="test",
    )
    tool_chain = [
        {
            "calls": [
                {
                    "name": "memorize",
                    "arguments": {"summary": "规则A"},
                    "result": "已记住（new:AbCDef12_34567890）：规则A",
                }
            ]
        }
    ]
    summaries, protected = worker._collect_explicit_memorized(tool_chain)
    assert summaries == ["规则A"]
    assert "AbCDef12_34567890" in protected


def test_collect_explicit_memorized_accepts_item_id_format():
    worker = PostResponseMemoryWorker(
        memorizer=cast(Any, _DummyMemorizer()),
        retriever=cast(Any, _DummyRetriever([])),
        light_provider=cast(Any, _DummyProvider()),
        light_model="test",
    )
    tool_chain = [
        {
            "calls": [
                {
                    "name": "memorize",
                    "arguments": {"summary": "规则B"},
                    "result": "已记住（item_id=memu_12345）：规则B",
                }
            ]
        }
    ]
    summaries, protected = worker._collect_explicit_memorized(tool_chain)
    assert summaries == ["规则B"]
    assert "memu_12345" in protected


def test_extract_invalidation_topics_skips_when_token_budget_exhausted():
    provider = _DummyProvider()
    worker = PostResponseMemoryWorker(
        memorizer=cast(Any, _DummyMemorizer()),
        retriever=cast(Any, _DummyRetriever([])),
        light_provider=cast(Any, provider),
        light_model="test",
    )
    topics, remain = asyncio.run(
        worker._extract_invalidation_topics("也许这个流程不对", token_budget=0)
    )
    assert topics == []
    assert remain == 0
    assert provider.calls == 0


def test_post_worker_keeps_run_context_isolated_across_concurrent_runs():
    class _Publisher:
        def __init__(self) -> None:
            self.events: list[MemoryWritten] = []

        async def fanout(self, event: MemoryWritten) -> None:
            self.events.append(event)

    class _StaticRetriever:
        async def retrieve(self, query: str, memory_types=None, **kwargs):
            return [{"id": f"{query}-1", "summary": f"{query} summary", "score": 0.95}]

    publisher = _Publisher()
    memorizer = _DummyMemorizer()
    worker = PostResponseMemoryWorker(
        memorizer=cast(Any, memorizer),
        retriever=cast(Any, _StaticRetriever()),
        light_provider=cast(Any, _DummyProvider()),
        light_model="test",
        event_publisher=cast(Any, publisher),
    )

    first_ready = asyncio.Event()
    second_ready = asyncio.Event()
    release = asyncio.Event()

    async def _extract(user_msg: str, token_budget: int):
        if user_msg == "first":
            first_ready.set()
            await second_ready.wait()
            await release.wait()
            return ["topic-a"], token_budget
        second_ready.set()
        await first_ready.wait()
        release.set()
        return ["topic-b"], token_budget

    async def _check(topic: str, candidates: list[dict], token_budget: int):
        return [str(candidates[0]["id"])], token_budget

    worker._extract_invalidation_topics = AsyncMock(side_effect=_extract)
    worker._check_invalidate = AsyncMock(side_effect=_check)

    async def _run() -> None:
        await asyncio.gather(
            worker.run(
                user_msg="first",
                agent_response="ok",
                tool_chain=[],
                source_ref="src-1",
                session_key="telegram:1",
                channel="telegram",
                chat_id="1",
                role_id="mira",
            ),
            worker.run(
                user_msg="second",
                agent_response="ok",
                tool_chain=[],
                source_ref="src-2",
                session_key="telegram:2",
                channel="telegram",
                chat_id="2",
                role_id="atlas",
            ),
        )

    asyncio.run(_run())

    assert memorizer.supersede_batch.call_count == 2
    assert [
        (event.session_key, event.chat_id, event.role_id, event.source_ref)
        for event in publisher.events
    ] == [
        ("telegram:2", "2", "atlas", "src-2"),
        ("telegram:1", "1", "mira", "src-1"),
    ]


def test_post_worker_invalidation_retrieval_uses_run_scope():
    retriever = _DummyRetriever(
        [{"id": "mem:1", "summary": "topic summary", "score": 0.95}]
    )
    worker = PostResponseMemoryWorker(
        memorizer=cast(Any, _DummyMemorizer()),
        retriever=cast(Any, retriever),
        light_provider=cast(Any, _DummyProvider()),
        light_model="test",
    )
    worker._extract_invalidation_topics = AsyncMock(
        return_value=(["topic"], worker.TOKEN_BUDGET_PER_RUN)
    )
    worker._check_invalidate = AsyncMock(return_value=([], worker.TOKEN_BUDGET_PER_RUN))

    asyncio.run(
        worker.run(
            user_msg="以后别再这么做",
            agent_response="好的",
            tool_chain=[],
            source_ref="src-1",
            session_key="telegram:1",
            channel="telegram",
            chat_id="1",
            role_id="mira",
        )
    )

    assert retriever.calls == [
        (
            "topic",
            ("procedure", "preference"),
            {
                "role_id": "mira",
                "scope_channel": "telegram",
                "scope_chat_id": "1",
                "require_scope_match": True,
            },
        )
    ]


def test_merge_item_should_keep_procedure_metadata_consistent():
    embedder = _StaticEmbedder(
        {
            "查 Steam 必须先用 steam_mcp，不能直接使用 web_search": [1.0, 0.0],
            "合并后的 Steam 查询规则：先用 steam_mcp，再补充区服确认": [0.9, 0.1],
        }
    )
    store = MemoryStore2(":memory:")
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
    embedder = _StaticEmbedder(
        {
            "查 Steam 必须直接使用 web_search": [1.0, 0.0],
            "查 Steam 必须先使用 steam_mcp": [0.9, 0.1],
        }
    )
    store = MemoryStore2(":memory:")
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
    embedder = _StaticEmbedder(
        {
            "Mira 视角：用户偏好中文回复": [1.0, 0.0],
            "Atlas 视角：用户偏好中文回复": [1.0, 0.0],
            "Mira 视角：用户更偏好简洁中文回复": [1.0, 0.0],
        }
    )
    store = MemoryStore2(":memory:")
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
