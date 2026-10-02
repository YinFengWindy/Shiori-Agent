from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest
from shiori_sdk.memory.committed import TurnCommitted
from shiori_sdk.memory.engine import (
    EngineProfile,
    MemoryCapability,
)
from shiori_sdk.memory.events import ConsolidationCommitted, TurnIngested
from shiori_sdk.testing.events import FakeEvents as EventBus
from shiori_sdk.testing.models import FakeModelResponse as LLMResponse

from plugins.default_memory.backend.engine.lifecycle import DefaultMemoryEngine
from plugins.default_memory.backend.semantic.store import MemoryStore2


async def test_default_memory_engine_handles_turn_committed_via_event_bus(make_engine):
    event_bus = EventBus()
    worker = SimpleNamespace(run=AsyncMock(), handle=AsyncMock())
    _ = make_engine(
        retriever=cast(Any, SimpleNamespace()),
        post_response_worker=cast(Any, worker),
        event_publisher=event_bus,
    )

    event_bus.enqueue(
        TurnCommitted(
            session_key="cli:1",
            channel="cli",
            chat_id="1",
            input_message="以后用中文",
            persisted_user_message="以后用中文",
            assistant_response="好的",
            tools_used=[],
            tool_chain_raw=[{"text": "memo", "calls": []}],
        )
    )
    await event_bus.drain()

    worker.handle.assert_awaited_once()
    event = worker.handle.await_args.args[0]
    assert isinstance(event, TurnIngested)
    assert event.session_key == "cli:1"
    assert event.tool_chain == [{"text": "memo", "calls": []}]
    await event_bus.aclose()


async def test_default_memory_engine_respects_skip_post_memory_event_flag(make_engine):
    event_bus = EventBus()
    worker = SimpleNamespace(run=AsyncMock(), handle=AsyncMock())
    _ = make_engine(
        retriever=cast(Any, SimpleNamespace()),
        post_response_worker=cast(Any, worker),
        event_publisher=event_bus,
    )

    event_bus.enqueue(
        TurnCommitted(
            session_key="cli:1",
            channel="cli",
            chat_id="1",
            input_message="以后用中文",
            persisted_user_message="以后用中文",
            assistant_response="好的",
            tools_used=[],
            extra={"skip_post_memory": True},
        )
    )
    await event_bus.drain()

    worker.handle.assert_not_awaited()
    await event_bus.aclose()


async def test_default_memory_engine_consumes_markdown_consolidation_event(make_engine):
    memorizer = SimpleNamespace(
        save_from_consolidation=AsyncMock(),
        save_item_with_supersede=AsyncMock(return_value="new:memu-1"),
    )
    provider = SimpleNamespace(
        chat=AsyncMock(
            return_value=SimpleNamespace(
                content='{"profile":[{"summary":"用户买了 Zigbee 网关","category":"purchase","emotional_weight":4}],"preference":[],"procedure":[]}'
            )
        )
    )
    engine = make_engine(
        provider=cast(Any, provider),
        memorizer=cast(Any, memorizer),
        v2_store=SimpleNamespace(list_items_for_admin=lambda **_kwargs: ([], 0)),
    )

    await engine._on_consolidation_committed(
        ConsolidationCommitted(
            history_entry_payloads=[("[2026-03-15 10:00] 用户聊了 Zigbee", 6)],
            source_ref='["m1"]',
            scope_channel="desktop",
            scope_chat_id="role:mira",
            conversation="USER: 我买了 Zigbee 网关",
            role_id="mira",
        )
    )

    memorizer.save_from_consolidation.assert_awaited_once()
    memorizer.save_item_with_supersede.assert_awaited_once()


async def test_default_memory_engine_consolidation_role_scope_persists_role_id(
    make_engine,
):
    memorizer = SimpleNamespace(
        save_from_consolidation=AsyncMock(),
        save_item_with_supersede=AsyncMock(return_value="new:memu-1"),
    )
    provider = SimpleNamespace(
        chat=AsyncMock(
            return_value=SimpleNamespace(
                content='{"profile":[{"summary":"用户买了 Zigbee 网关","category":"purchase","emotional_weight":4}],"preference":[],"procedure":[]}'
            )
        )
    )
    engine = make_engine(
        provider=cast(Any, provider),
        memorizer=cast(Any, memorizer),
        v2_store=SimpleNamespace(list_items_for_admin=lambda **_kwargs: ([], 0)),
    )

    await engine._on_consolidation_committed(
        ConsolidationCommitted(
            history_entry_payloads=[("[2026-03-15 10:00] 用户聊了 Zigbee", 6)],
            source_ref='["m1"]',
            scope_channel="cli",
            scope_chat_id="1",
            conversation="USER: 我买了 Zigbee 网关",
            role_id="mira",
        )
    )

    assert memorizer.save_from_consolidation.await_args.kwargs["role_id"] == "mira"
    assert (
        memorizer.save_item_with_supersede.await_args.kwargs["extra"]["role_id"]
        == "mira"
    )


async def test_default_memory_engine_reports_implicit_extraction_failure(make_engine):
    memorizer = SimpleNamespace(
        save_from_consolidation=AsyncMock(),
        save_item_with_supersede=AsyncMock(return_value="new:memu-1"),
    )
    provider = SimpleNamespace(
        chat=AsyncMock(return_value=SimpleNamespace(content="not json"))
    )
    engine = make_engine(
        provider=cast(Any, provider),
        memorizer=cast(Any, memorizer),
        v2_store=SimpleNamespace(list_items_for_admin=lambda **_kwargs: ([], 0)),
    )

    with pytest.raises(RuntimeError, match="long_term extraction failed"):
        await engine._on_consolidation_committed(
            ConsolidationCommitted(
                history_entry_payloads=[("[2026-03-15 10:00] 用户聊了 Zigbee", 6)],
                source_ref='["m1"]',
                scope_channel="cli",
                scope_chat_id="1",
                conversation="USER: 我买了 Zigbee 网关",
                role_id="mira",
            )
        )

    memorizer.save_from_consolidation.assert_awaited_once()
    memorizer.save_item_with_supersede.assert_not_awaited()


def test_default_memory_engine_descriptor_keeps_messages_capability_only():
    descriptor = DefaultMemoryEngine.DESCRIPTOR

    assert descriptor.profile == EngineProfile.RICH_MEMORY_ENGINE
    assert MemoryCapability.INGEST_MESSAGES in descriptor.capabilities
    assert MemoryCapability.INGEST_TEXT not in descriptor.capabilities


async def test_implicit_long_term_extraction_uses_auxiliary_budget(monkeypatch):
    provider = AsyncMock()
    provider.chat.return_value = LLMResponse(
        content='{"preference":[{"summary":"你喜欢拿铁"}]}'
    )
    engine = DefaultMemoryEngine.__new__(DefaultMemoryEngine)
    monkeypatch.setattr(engine, "_provider", provider, raising=False)
    monkeypatch.setattr(
        engine, "_config", SimpleNamespace(model="memory-model"), raising=False
    )

    result = await engine._extract_implicit_long_term(conversation="USER: 我喜欢拿铁")

    assert result == {"preference": [{"summary": "你喜欢拿铁"}]}
    request = provider.chat.await_args.kwargs
    assert request["call_purpose"] == "auxiliary"
    assert request["max_tokens"] == 600


@pytest.mark.asyncio
async def test_post_response_extraction_receives_current_role_memory(tmp_path) -> None:
    store = MemoryStore2(tmp_path / "memory2.db")
    try:
        store.upsert_item(
            "preference",
            "你喜欢拿铁",
            embedding=None,
            extra={"role_id": "mira"},
        )
        store.upsert_item(
            "preference",
            "你喜欢红茶",
            embedding=None,
            extra={"role_id": "atlas"},
        )
        engine = object.__new__(DefaultMemoryEngine)
        engine._v2_store = store
        engine._extract_implicit_long_term = AsyncMock(return_value=None)

        await engine._extract_and_save_post_response(
            user_msg="我还喜欢摩卡",
            assistant_response="记住了",
            source_ref="role:mira@post_response",
            channel="desktop",
            chat_id="role:mira",
            role_id="mira",
        )

        existing_profile = engine._extract_implicit_long_term.await_args.kwargs[
            "existing_profile"
        ]
        assert "你喜欢拿铁" in existing_profile
        assert "你喜欢红茶" not in existing_profile
    finally:
        store.close()


@pytest.mark.asyncio
async def test_consolidation_waits_for_sibling_writes_before_propagating_failure():
    import asyncio

    from shiori_sdk.memory.events import ConsolidationCommitted

    engine = DefaultMemoryEngine.__new__(DefaultMemoryEngine)
    entered, release, finished = asyncio.Event(), asyncio.Event(), asyncio.Event()
    failure = ValueError("first save failed")

    async def save(*, history_entry, **kwargs):
        if history_entry == "fail":
            await entered.wait()
            raise failure
        entered.set()
        await release.wait()
        finished.set()

    engine._save_from_consolidation = save
    implicit = AsyncMock()
    engine._extract_implicit_long_term = implicit
    task = asyncio.create_task(
        engine._on_consolidation_committed(
            ConsolidationCommitted(
                [("fail", 0), ("slow", 0)],
                "source",
                "desktop",
                "1",
                "conversation",
                "mira",
            )
        )
    )
    await entered.wait()
    for _ in range(5):
        await asyncio.sleep(0)
    assert not task.done()
    release.set()
    with pytest.raises(ValueError) as result:
        await task
    assert result.value is failure
    assert finished.is_set()
    implicit.assert_not_awaited()
