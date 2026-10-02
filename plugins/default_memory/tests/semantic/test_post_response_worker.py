from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from shiori_sdk.memory.events import MemoryWritten, TurnIngested

from plugins.default_memory.backend.semantic.post_response_worker import (
    PostResponseMemoryWorker,
)


class _Resp_post_response_worker:
    def __init__(self, content: str) -> None:
        self.content = content


class _DummyProvider_post_response_worker:
    def __init__(self):
        self.calls = 0

    async def chat(self, **kwargs):
        self.calls += 1
        raise AssertionError("provider.chat should not be called in this test")


class _DummyRetriever_post_response_worker:
    def __init__(self, results):
        self._results = results
        self.calls = []

    async def retrieve(self, query: str, memory_types=None, **kwargs):
        self.calls.append((query, tuple(memory_types or []), dict(kwargs)))
        return list(self._results)


class _DummyMemorizer_post_response_worker:
    def __init__(self, store=None):
        from unittest.mock import AsyncMock, MagicMock

        self.save_item = AsyncMock(return_value="new:testid")
        self.supersede_batch = MagicMock()
        self.merge_item = AsyncMock()
        self._store = store


def test_post_worker_without_implicit_handler_only_handles_invalidations():
    from unittest.mock import AsyncMock

    memorizer = _DummyMemorizer_post_response_worker()
    retriever = _DummyRetriever_post_response_worker([])
    worker = PostResponseMemoryWorker(
        memorizer=cast(Any, memorizer),
        retriever=cast(Any, retriever),
        light_provider=cast(Any, _DummyProvider_post_response_worker()),
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
            role_id="mira",
        )
    )

    # run() 不再写入任何隐式记忆
    memorizer.save_item.assert_not_called()
    # 但 invalidation 检查仍然运行
    worker._handle_invalidations.assert_awaited_once()


def test_post_worker_protects_item_id_from_structured_memorize_result():
    worker = PostResponseMemoryWorker(
        memorizer=cast(Any, _DummyMemorizer_post_response_worker()),
        retriever=cast(Any, _DummyRetriever_post_response_worker([])),
        light_provider=cast(Any, _DummyProvider_post_response_worker()),
        light_model="test",
    )
    worker._handle_invalidations = AsyncMock(return_value=worker.TOKEN_BUDGET_PER_RUN)

    asyncio.run(
        worker.run(
            user_msg="记住我喜欢拿铁",
            agent_response="好",
            tool_chain=[
                {
                    "calls": [
                        {
                            "name": "memorize",
                            "arguments": {"summary": "你喜欢拿铁"},
                            "result": (
                                '{"item_id":"memu_12345","memory_kind":"preference",'
                                '"status":"new","summary":"你喜欢拿铁"}'
                            ),
                        }
                    ]
                }
            ],
            source_ref="test@post_response",
            role_id="mira",
        )
    )

    protected_ids = worker._handle_invalidations.await_args.args[2]
    assert protected_ids == {"memu_12345"}


def test_post_worker_skips_implicit_extraction_when_budget_is_exhausted():
    implicit_handler = AsyncMock()
    worker = PostResponseMemoryWorker(
        memorizer=cast(Any, _DummyMemorizer_post_response_worker()),
        retriever=cast(Any, _DummyRetriever_post_response_worker([])),
        light_provider=cast(Any, _DummyProvider_post_response_worker()),
        light_model="test",
        implicit_memory_handler=implicit_handler,
    )
    worker._handle_invalidations = AsyncMock(
        return_value=worker.TOKENS_EXTRACT_IMPLICIT - 1
    )

    asyncio.run(
        worker.run(
            user_msg="我喜欢拿铁",
            agent_response="记住了",
            tool_chain=[],
            source_ref="test@post_response",
            role_id="mira",
        )
    )

    implicit_handler.assert_not_awaited()


def test_post_worker_propagates_implicit_extraction_failure():
    implicit_handler = AsyncMock(side_effect=RuntimeError("extract failed"))
    worker = PostResponseMemoryWorker(
        memorizer=cast(Any, _DummyMemorizer_post_response_worker()),
        retriever=cast(Any, _DummyRetriever_post_response_worker([])),
        light_provider=cast(Any, _DummyProvider_post_response_worker()),
        light_model="test",
        implicit_memory_handler=implicit_handler,
    )
    worker._handle_invalidations = AsyncMock(return_value=worker.TOKEN_BUDGET_PER_RUN)

    with pytest.raises(RuntimeError, match="extract failed"):
        asyncio.run(
            worker.run(
                user_msg="我喜欢拿铁",
                agent_response="记住了",
                tool_chain=[],
                source_ref="test@post_response",
                role_id="mira",
            )
        )


def test_post_worker_handle_delegates_turn_ingested_event():
    worker = PostResponseMemoryWorker(
        memorizer=cast(Any, _DummyMemorizer_post_response_worker()),
        retriever=cast(Any, _DummyRetriever_post_response_worker([])),
        light_provider=cast(Any, _DummyProvider_post_response_worker()),
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


def test_collect_explicit_memorized_accepts_long_mixed_id():
    worker = PostResponseMemoryWorker(
        memorizer=cast(Any, _DummyMemorizer_post_response_worker()),
        retriever=cast(Any, _DummyRetriever_post_response_worker([])),
        light_provider=cast(Any, _DummyProvider_post_response_worker()),
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
        memorizer=cast(Any, _DummyMemorizer_post_response_worker()),
        retriever=cast(Any, _DummyRetriever_post_response_worker([])),
        light_provider=cast(Any, _DummyProvider_post_response_worker()),
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


def test_consume_budget_reports_affordability_and_remaining_tokens():
    worker = PostResponseMemoryWorker(
        memorizer=cast(Any, _DummyMemorizer_post_response_worker()),
        retriever=cast(Any, _DummyRetriever_post_response_worker([])),
        light_provider=cast(Any, _DummyProvider_post_response_worker()),
        light_model="test",
    )

    assert worker._consume_budget(10, 3) == (True, 7)


def test_extract_invalidation_topics_returns_topics_parsed_from_light_model():
    provider = SimpleNamespace(
        chat=AsyncMock(return_value=_Resp_post_response_worker('["topic"]'))
    )
    worker = PostResponseMemoryWorker(
        memorizer=cast(Any, _DummyMemorizer_post_response_worker()),
        retriever=cast(Any, _DummyRetriever_post_response_worker([])),
        light_provider=cast(Any, provider),
        light_model="test",
    )

    topics, _remain = asyncio.run(
        worker._extract_invalidation_topics("你之前这个流程错了", 700)
    )

    assert topics == ["topic"]
    request = provider.chat.await_args.kwargs
    assert request["call_purpose"] == "auxiliary"
    assert request["max_tokens"] == 96


def test_check_invalidate_returns_ids_selected_by_light_model():
    provider = SimpleNamespace(
        chat=AsyncMock(return_value=_Resp_post_response_worker('["x1"]'))
    )
    worker = PostResponseMemoryWorker(
        memorizer=cast(Any, _DummyMemorizer_post_response_worker()),
        retriever=cast(Any, _DummyRetriever_post_response_worker([])),
        light_provider=cast(Any, provider),
        light_model="test",
    )

    ids, _remain = asyncio.run(
        worker._check_invalidate("topic", [{"id": "x1", "summary": "旧规则"}], 700)
    )

    assert ids == ["x1"]
    request = provider.chat.await_args.kwargs
    assert request["call_purpose"] == "auxiliary"
    assert request["max_tokens"] == 96


def test_extract_invalidation_topics_skips_when_token_budget_exhausted():
    provider = _DummyProvider_post_response_worker()
    worker = PostResponseMemoryWorker(
        memorizer=cast(Any, _DummyMemorizer_post_response_worker()),
        retriever=cast(Any, _DummyRetriever_post_response_worker([])),
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
    memorizer = _DummyMemorizer_post_response_worker()
    worker = PostResponseMemoryWorker(
        memorizer=cast(Any, memorizer),
        retriever=cast(Any, _StaticRetriever()),
        light_provider=cast(Any, _DummyProvider_post_response_worker()),
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
    retriever = _DummyRetriever_post_response_worker(
        [{"id": "mem:1", "summary": "topic summary", "score": 0.95}]
    )
    worker = PostResponseMemoryWorker(
        memorizer=cast(Any, _DummyMemorizer_post_response_worker()),
        retriever=cast(Any, retriever),
        light_provider=cast(Any, _DummyProvider_post_response_worker()),
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


class _DummyProvider_post_response_profile:
    async def chat(self, **kwargs):
        raise AssertionError("provider.chat should not be called in this test")


class _DummyRetriever_post_response_profile:
    def __init__(self, results):
        self._results = list(results)
        self.calls = []

    async def retrieve(self, query: str, memory_types=None, top_k=None):
        self.calls.append((query, tuple(memory_types or []), top_k))
        return list(self._results)


class _DummyMemorizer_post_response_profile:
    def __init__(self, store=None):
        self.save_item = AsyncMock(return_value="new:testid")
        self.supersede_batch = MagicMock()
        self._store = store


def test_worker_without_implicit_handler_does_not_extract_profile():
    """A worker without an implicit handler only performs invalidation work."""
    memorizer = _DummyMemorizer_post_response_profile()
    retriever = _DummyRetriever_post_response_profile([])
    worker = PostResponseMemoryWorker(
        memorizer=cast(Any, memorizer),
        retriever=cast(Any, retriever),
        light_provider=cast(Any, _DummyProvider_post_response_profile()),
        light_model="test",
    )
    worker._handle_invalidations = AsyncMock(
        side_effect=lambda *args, **kwargs: args[-1]
    )

    asyncio.run(
        worker.run(
            user_msg="我刚买了一个新键盘",
            agent_response="记住了",
            tool_chain=[],
            source_ref="test@post_response",
            role_id="mira",
        )
    )

    memorizer.save_item.assert_not_called()
