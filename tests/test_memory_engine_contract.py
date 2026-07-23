from __future__ import annotations
from typing import Any, cast

import asyncio
from datetime import datetime
import pytest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from bus.event_bus import EventBus
from bus.events_lifecycle import TurnCommitted
from agent.config_models import Config, MemoryConfig
from agent.tools.registry import ToolRegistry
from bootstrap.memory import build_memory_runtime
from plugins.default_memory.engine import DefaultMemoryEngine
from core.memory.engine import (
    EngineProfile,
    MemoryCapability,
    MemoryIngestRequest,
    MemoryMutation,
    MemoryQuery,
    MemoryQueryFilters,
    MemoryScope,
)
from core.memory.events import ConsolidationCommitted, TurnIngested
from core.memory.markdown import (
    ConsolidateRequest,
    ConsolidateResult,
    _ConsolidationDraft,
    _ConsolidationFailure,
    _ConsolidationWindow,
    MarkdownMemoryMaintenance,
    MarkdownMemoryStore,
    MemoryLifecycleBindRequest,
    resolve_markdown_store,
)
from core.memory.plugin import MemoryPluginRuntime
from memory2.store import MemoryStore2


def _make_default_engine(
    *,
    config=None,
    provider=None,
    retriever=None,
    memorizer=None,
    tagger=None,
    post_response_worker=None,
    event_publisher=None,
):
    engine = DefaultMemoryEngine.__new__(DefaultMemoryEngine)
    engine._config = config or SimpleNamespace(model="lm")
    engine._workspace = Path(".")
    engine._provider = provider
    engine._light_provider = None
    engine._light_model = ""
    engine._v2_store = None
    engine._embedder = None
    engine._memorizer = memorizer
    engine._retriever = retriever
    engine._tagger = tagger
    engine._post_response_worker = post_response_worker
    engine._event_bus = event_publisher
    engine.closeables = []
    engine._wire_memory2_events()
    return engine


async def _drain_maintenance(maintenance: object) -> None:
    for _ in range(5):
        tasks = list(getattr(maintenance, "_maintenance_tasks").values())
        if not tasks:
            return
        await asyncio.gather(*tasks)
        await asyncio.sleep(0)


async def test_default_memory_engine_retrieve_maps_hits_and_text_block():
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
    engine = _make_default_engine(retriever=cast(Any, retriever))

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


def test_resolve_markdown_store_requires_role_id(tmp_path: Path):
    with pytest.raises(ValueError, match="role_id required for markdown memory access"):
        resolve_markdown_store(workspace=tmp_path)


async def test_default_memory_engine_retrieve_keeps_raw_items_and_mode_trace():
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
    engine = _make_default_engine(retriever=cast(Any, retriever))

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


async def test_default_memory_engine_interest_preserves_read_only_effect():
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
    engine = _make_default_engine(retriever=cast(Any, retriever))

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


async def test_default_memory_engine_retrieve_falls_back_to_session_scope():
    retriever = SimpleNamespace(
        retrieve=AsyncMock(return_value=[]),
        build_injection_block=lambda items: ("", []),
    )
    engine = _make_default_engine(retriever=cast(Any, retriever))

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
    tmp_path: Path,
):
    provider = SimpleNamespace()
    runtime = build_memory_runtime(
        config=Config(
            provider="test",
            model="gpt-test",
            api_key="k",
            system_prompt="hi",
            memory=MemoryConfig(enabled=True),
        ),
        workspace=tmp_path,
        tools=ToolRegistry(),
        provider=cast(Any, provider),
        light_provider=None,
        http_resources=cast(Any, SimpleNamespace(external_default=SimpleNamespace())),
    )
    engine = cast(Any, runtime.engine)
    store = engine._v2_store
    assert store is not None

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
    tmp_path: Path,
):
    provider = SimpleNamespace()
    runtime = build_memory_runtime(
        config=Config(
            provider="test",
            model="gpt-test",
            api_key="k",
            system_prompt="hi",
            memory=MemoryConfig(enabled=True),
        ),
        workspace=tmp_path,
        tools=ToolRegistry(),
        provider=cast(Any, provider),
        light_provider=None,
        http_resources=cast(Any, SimpleNamespace(external_default=SimpleNamespace())),
    )
    engine = cast(Any, runtime.engine)
    store = engine._v2_store
    assert store is not None

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


async def test_default_engine_keeps_history_injected_ids():
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
    engine = _make_default_engine(retriever=cast(Any, retriever))

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


async def test_default_memory_engine_ingest_delegates_to_post_worker():
    worker = SimpleNamespace(run=AsyncMock())
    engine = _make_default_engine(
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


async def test_default_memory_engine_handles_turn_committed_via_event_bus():
    event_bus = EventBus()
    worker = SimpleNamespace(run=AsyncMock(), handle=AsyncMock())
    _ = _make_default_engine(
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


async def test_default_memory_engine_respects_skip_post_memory_event_flag():
    event_bus = EventBus()
    worker = SimpleNamespace(run=AsyncMock(), handle=AsyncMock())
    _ = _make_default_engine(
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


def test_markdown_maintenance_respects_skip_post_memory_event_flag():
    maintenance = MarkdownMemoryMaintenance.__new__(MarkdownMemoryMaintenance)
    maintenance._enqueue_maintenance = MagicMock()

    maintenance.on_turn_committed(
        TurnCommitted(
            session_key="scheduler:job",
            channel="telegram",
            chat_id="1",
            input_message="天气",
            persisted_user_message=None,
            assistant_response="不带伞",
            tools_used=[],
            extra={"skip_post_memory": True},
        )
    )

    maintenance._enqueue_maintenance.assert_not_called()


@pytest.mark.asyncio
async def test_markdown_maintenance_records_background_consolidation_failure(tmp_path: Path):
    session = SimpleNamespace(
        key="role:mira",
        metadata={"role_id": "mira"},
        messages=[{"role": "user", "content": f"u{i}"} for i in range(30)],
        last_consolidated=0,
    )
    maintenance = MarkdownMemoryMaintenance(
        store=MarkdownMemoryStore(tmp_path),
        provider=cast(Any, SimpleNamespace()),
        model="lm",
        keep_count=20,
    )
    maintenance._worker.prepare_consolidation = AsyncMock(
        return_value=_ConsolidationFailure(
            step="event",
            error="provider timeout",
            elapsed_ms=100,
        )
    )
    maintenance.bind_lifecycle(
        MemoryLifecycleBindRequest(
            get_session=lambda _key: session,
            save_session=AsyncMock(),
        )
    )

    maintenance.request_background_consolidation(session.key)
    await _drain_maintenance(maintenance)

    assert maintenance.get_consolidation_failure(session.key) == "provider timeout"

    maintenance._worker.prepare_consolidation = AsyncMock(return_value=None)
    await maintenance.consolidate(ConsolidateRequest(session=session))

    assert maintenance.get_consolidation_failure(session.key) is None


@pytest.mark.asyncio
async def test_markdown_maintenance_background_request_does_not_wait(tmp_path: Path):
    started = asyncio.Event()
    release = asyncio.Event()
    session = SimpleNamespace(
        key="role:mira",
        metadata={"role_id": "mira"},
        messages=[{"role": "user", "content": f"u{i}"} for i in range(30)],
        last_consolidated=0,
    )
    maintenance = MarkdownMemoryMaintenance(
        store=MarkdownMemoryStore(tmp_path),
        provider=cast(Any, SimpleNamespace()),
        model="lm",
        keep_count=20,
    )

    async def _slow_prepare(*args, **kwargs):
        started.set()
        await release.wait()
        return None

    maintenance._worker.prepare_consolidation = _slow_prepare
    maintenance.bind_lifecycle(
        MemoryLifecycleBindRequest(
            get_session=lambda _key: session,
            save_session=AsyncMock(),
        )
    )

    maintenance.request_background_consolidation(session.key)
    await asyncio.wait_for(started.wait(), timeout=1)

    assert session.key in maintenance._maintenance_tasks
    release.set()
    await _drain_maintenance(maintenance)


async def test_default_memory_engine_refreshes_recent_context_from_lifecycle_role_only():
    event_bus = EventBus()
    session = SimpleNamespace(
        key="role:mira",
        metadata={"role_id": "mira"},
        messages=[{"role": "user", "content": "u"}],
        last_consolidated=0,
    )
    maintenance = MarkdownMemoryMaintenance(
        store=MarkdownMemoryStore(Path(".")),
        provider=cast(Any, SimpleNamespace()),
        model="lm",
        keep_count=20,
        event_bus=event_bus,
    )
    maintenance.refresh_recent_turns = AsyncMock()
    save_session = AsyncMock()
    maintenance.bind_lifecycle(
        MemoryLifecycleBindRequest(
            get_session=lambda _key: session,
            save_session=save_session,
        )
    )

    event_bus.enqueue(
        TurnCommitted(
            session_key="role:mira",
            channel="desktop",
            chat_id="role:mira",
            input_message="hi",
            persisted_user_message="hi",
            assistant_response="ok",
            tools_used=[],
            role_id="mira",
        )
    )
    await event_bus.drain()
    await _drain_maintenance(maintenance)

    maintenance.refresh_recent_turns.assert_awaited_once()
    save_session.assert_not_awaited()
    await event_bus.aclose()


async def test_default_memory_engine_refreshes_role_recent_context_in_role_memory(
    tmp_path: Path,
):
    event_bus = EventBus()
    session = SimpleNamespace(
        key="role:mira",
        metadata={"role_id": "mira"},
        messages=[
            {"role": "user", "content": "你好"},
            {"role": "assistant", "content": "嗯。"},
        ],
        last_consolidated=0,
    )
    maintenance = MarkdownMemoryMaintenance(
        store=MarkdownMemoryStore(tmp_path),
        provider=cast(Any, SimpleNamespace()),
        model="lm",
        keep_count=20,
        event_bus=event_bus,
    )
    save_session = AsyncMock()
    maintenance.bind_lifecycle(
        MemoryLifecycleBindRequest(
            get_session=lambda _key: session,
            save_session=save_session,
        )
    )

    event_bus.enqueue(
        TurnCommitted(
            session_key="role:mira",
            channel="desktop",
            chat_id="role:mira",
            input_message="你好",
            persisted_user_message="你好",
            assistant_response="嗯。",
            tools_used=[],
            role_id="mira",
        )
    )
    await event_bus.drain()
    await _drain_maintenance(maintenance)

    role_recent_context_path = (
        tmp_path / "roles" / "mira" / "memory" / "RECENT_CONTEXT.md"
    )
    global_recent_context_path = tmp_path / "memory" / "RECENT_CONTEXT.md"

    assert role_recent_context_path.exists()
    assert "你好" in role_recent_context_path.read_text(encoding="utf-8")
    assert "嗯。" in role_recent_context_path.read_text(encoding="utf-8")
    assert not global_recent_context_path.exists()
    save_session.assert_not_awaited()
    await event_bus.aclose()


async def test_default_memory_engine_consolidates_ready_session_from_lifecycle():
    event_bus = EventBus()
    session = SimpleNamespace(
        key="role:mira",
        metadata={"role_id": "mira"},
        messages=[{"role": "user", "content": "u"}] * 31,
        last_consolidated=0,
    )
    maintenance = MarkdownMemoryMaintenance(
        store=MarkdownMemoryStore(Path(".")),
        provider=cast(Any, SimpleNamespace()),
        model="lm",
        keep_count=20,
        event_bus=event_bus,
    )
    maintenance._consolidate_unlocked = AsyncMock(
        return_value=ConsolidateResult(trace={"mode": "markdown"})
    )
    save_session = AsyncMock()
    maintenance.bind_lifecycle(
        MemoryLifecycleBindRequest(
            get_session=lambda _key: session,
            save_session=save_session,
        )
    )

    event_bus.enqueue(
        TurnCommitted(
            session_key="role:mira",
            channel="desktop",
            chat_id="role:mira",
            input_message="hi",
            persisted_user_message="hi",
            assistant_response="ok",
            tools_used=[],
            role_id="mira",
        )
    )
    await event_bus.drain()
    await _drain_maintenance(maintenance)

    maintenance._consolidate_unlocked.assert_awaited_once()
    save_session.assert_awaited_once_with(session)
    await event_bus.aclose()


async def test_markdown_consolidation_advances_window_when_consumer_fails(
    tmp_path: Path,
):
    event_bus = EventBus()

    async def _fail_consolidation(_event):
        raise RuntimeError("vector write failed")

    event_bus.on(ConsolidationCommitted, _fail_consolidation)
    session = SimpleNamespace(
        key="role:mira",
        metadata={"role_id": "mira"},
        messages=[{"role": "user", "content": "u"}] * 12,
        last_consolidated=0,
    )
    maintenance = MarkdownMemoryMaintenance(
        store=MarkdownMemoryStore(tmp_path),
        provider=cast(Any, SimpleNamespace()),
        model="lm",
        keep_count=6,
        event_bus=event_bus,
    )
    draft = _ConsolidationDraft(
        window=_ConsolidationWindow(
            old_messages=list(session.messages[:6]),
            keep_count=6,
            consolidate_up_to=6,
        ),
        source_ref='["role:mira:0"]',
        history_entry_payloads=[("[2026-05-05 13:00] 用户测试记忆", 0)],
        pending_items="",
        conversation="USER: 测试记忆",
        recent_context_text="# Recent Context\n",
        scope_channel="desktop",
        scope_chat_id="role:mira",
    )
    maintenance._worker.prepare_consolidation = AsyncMock(return_value=draft)

    with pytest.raises(RuntimeError, match="vector write failed"):
        await maintenance.consolidate(ConsolidateRequest(session=session))

    assert session.last_consolidated == 6
    assert "用户测试记忆" in (
        tmp_path / "roles" / "mira" / "memory" / "HISTORY.md"
    ).read_text(encoding="utf-8")
    await event_bus.aclose()


async def test_markdown_consolidation_failure_trace_does_not_advance_cursor(
    tmp_path: Path,
):
    session = SimpleNamespace(
        key="role:mira",
        metadata={"role_id": "mira"},
        messages=[{"role": "user", "content": f"u{i}"} for i in range(8)],
        last_consolidated=0,
    )
    maintenance = MarkdownMemoryMaintenance(
        store=MarkdownMemoryStore(tmp_path),
        provider=cast(Any, SimpleNamespace()),
        model="lm",
        keep_count=4,
    )
    maintenance._worker.prepare_consolidation = AsyncMock(
        return_value=_ConsolidationFailure(
            step="recent_context",
            error="TimeoutError",
            elapsed_ms=180000,
        )
    )

    result = await maintenance.consolidate(ConsolidateRequest(session=session))

    assert result.consolidated_count == 0
    assert result.trace == {
        "mode": "failed",
        "step": "recent_context",
        "error": "TimeoutError",
        "elapsed_ms": 180000,
    }
    assert session.last_consolidated == 0


async def test_markdown_consolidation_runs_post_consolidation_hook(tmp_path: Path):
    session = SimpleNamespace(
        key="role:mira",
        metadata={"role_id": "mira"},
        messages=[{"role": "user", "content": f"u{i}"} for i in range(12)],
        last_consolidated=0,
    )
    maintenance = MarkdownMemoryMaintenance(
        store=MarkdownMemoryStore(tmp_path),
        provider=cast(Any, SimpleNamespace()),
        model="lm",
        keep_count=6,
    )
    draft = _ConsolidationDraft(
        window=_ConsolidationWindow(
            old_messages=list(session.messages[:6]),
            keep_count=6,
            consolidate_up_to=6,
        ),
        source_ref='["role:mira:0"]',
        history_entry_payloads=[],
        pending_items="",
        conversation="USER: hi",
        recent_context_text="# Recent Context\n",
        scope_channel="desktop",
        scope_chat_id="role:mira",
    )
    maintenance._worker.prepare_consolidation = AsyncMock(return_value=draft)
    after_consolidation = AsyncMock()
    maintenance.bind_lifecycle(
        MemoryLifecycleBindRequest(
            get_session=lambda _key: session,
            save_session=AsyncMock(),
            after_consolidation=after_consolidation,
        )
    )

    result = await maintenance.consolidate(ConsolidateRequest(session=session))

    assert result.trace["mode"] == "markdown"
    after_consolidation.assert_awaited_once_with(session)


async def test_markdown_consolidation_ignores_post_consolidation_hook_failure(
    tmp_path: Path,
):
    session = SimpleNamespace(
        key="role:mira",
        metadata={"role_id": "mira"},
        messages=[{"role": "user", "content": f"u{i}"} for i in range(12)],
        last_consolidated=0,
    )
    maintenance = MarkdownMemoryMaintenance(
        store=MarkdownMemoryStore(tmp_path),
        provider=cast(Any, SimpleNamespace()),
        model="lm",
        keep_count=6,
    )
    draft = _ConsolidationDraft(
        window=_ConsolidationWindow(
            old_messages=list(session.messages[:6]),
            keep_count=6,
            consolidate_up_to=6,
        ),
        source_ref='["role:mira:0"]',
        history_entry_payloads=[],
        pending_items="",
        conversation="USER: hi",
        recent_context_text="# Recent Context\n",
        scope_channel="desktop",
        scope_chat_id="role:mira",
    )
    maintenance._worker.prepare_consolidation = AsyncMock(return_value=draft)

    async def _fail(_session: object) -> None:
        raise RuntimeError("relationship refresh failed")

    maintenance.bind_lifecycle(
        MemoryLifecycleBindRequest(
            get_session=lambda _key: session,
            save_session=AsyncMock(),
            after_consolidation=_fail,
        )
    )

    result = await maintenance.consolidate(ConsolidateRequest(session=session))

    assert result.trace["mode"] == "markdown"
    assert session.last_consolidated == 6


async def test_default_memory_engine_serializes_lifecycle_maintenance():
    event_bus = EventBus()
    session = SimpleNamespace(
        key="role:mira",
        metadata={"role_id": "mira"},
        messages=[{"role": "user", "content": "u"}],
        last_consolidated=0,
    )
    maintenance = MarkdownMemoryMaintenance(
        store=MarkdownMemoryStore(Path(".")),
        provider=cast(Any, SimpleNamespace()),
        model="lm",
        keep_count=20,
        event_bus=event_bus,
    )
    active = 0
    max_active = 0
    first_started = asyncio.Event()
    release_first = asyncio.Event()

    async def _refresh_recent_turns(_request) -> None:
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        if max_active == 1:
            first_started.set()
            await release_first.wait()
        active -= 1

    maintenance.refresh_recent_turns = AsyncMock(side_effect=_refresh_recent_turns)
    maintenance.bind_lifecycle(
        MemoryLifecycleBindRequest(
            get_session=lambda _key: session,
            save_session=AsyncMock(),
        )
    )

    event_bus.enqueue(
        TurnCommitted(
            session_key="role:mira",
            channel="desktop",
            chat_id="role:mira",
            input_message="a",
            persisted_user_message="a",
            assistant_response="ok",
            tools_used=[],
            role_id="mira",
        )
    )
    await event_bus.drain()
    await first_started.wait()
    event_bus.enqueue(
        TurnCommitted(
            session_key="role:mira",
            channel="desktop",
            chat_id="role:mira",
            input_message="b",
            persisted_user_message="b",
            assistant_response="ok",
            tools_used=[],
            role_id="mira",
        )
    )
    await event_bus.drain()
    release_first.set()
    await _drain_maintenance(maintenance)

    assert max_active == 1
    assert maintenance.refresh_recent_turns.await_count == 2
    await event_bus.aclose()


async def test_default_memory_engine_remember_uses_memorizer():
    memorizer = SimpleNamespace(
        save_item_with_supersede=AsyncMock(return_value="new:memu-1")
    )
    engine = _make_default_engine(
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


async def test_default_memory_engine_remember_forwards_happened_at():
    memorizer = SimpleNamespace(
        save_item_with_supersede=AsyncMock(return_value="new:event-1")
    )
    engine = _make_default_engine(
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


async def test_default_memory_engine_remember_keeps_explicit_memory_domain():
    memorizer = SimpleNamespace(
        save_item_with_supersede=AsyncMock(return_value="new:memu-1")
    )
    engine = _make_default_engine(
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


async def test_default_memory_engine_remember_role_scope_persists_role_id():
    memorizer = SimpleNamespace(
        save_item_with_supersede=AsyncMock(return_value="new:memu-1")
    )
    engine = _make_default_engine(
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


async def test_default_memory_engine_query_passes_memory_domains():
    retriever = SimpleNamespace(
        retrieve=AsyncMock(return_value=[]),
        build_injection_block=lambda items: ("", []),
    )
    engine = _make_default_engine(retriever=cast(Any, retriever))

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


async def test_default_memory_engine_rejects_unauthorized_shared_write(tmp_path: Path):
    memorizer = SimpleNamespace(
        save_item_with_supersede=AsyncMock(return_value="new:memu-1")
    )
    engine = _make_default_engine(
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


async def test_default_memory_engine_allows_authorized_shared_write(tmp_path: Path):
    from core.roles import RoleStore

    RoleStore(tmp_path).create_role(
        role_id="mira",
        name="Mira",
        description="",
        system_prompt="you are mira",
        runtime_config={"shared_memory_enabled": True},
    )
    memorizer = SimpleNamespace(
        save_item_with_supersede=AsyncMock(return_value="new:memu-1")
    )
    engine = _make_default_engine(
        retriever=cast(Any, SimpleNamespace()),
        memorizer=cast(Any, memorizer),
    )
    engine._workspace = tmp_path

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


async def test_default_memory_engine_filters_unauthorized_shared_query(tmp_path: Path):
    retriever = SimpleNamespace(
        retrieve=AsyncMock(return_value=[]),
        build_injection_block=lambda items: ("", []),
    )
    engine = _make_default_engine(retriever=cast(Any, retriever))
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


async def test_default_memory_engine_forget_filters_to_matching_role_and_scope(
    tmp_path: Path,
):
    store = MemoryStore2(tmp_path / "memory2.db")
    engine = _make_default_engine(retriever=cast(Any, SimpleNamespace()))
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


async def test_default_memory_engine_remember_merged_keeps_target_id_alive():
    memorizer = SimpleNamespace(
        save_item_with_supersede=AsyncMock(return_value="merged:memu-1")
    )
    engine = _make_default_engine(
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


async def test_default_memory_engine_timeline_query_honors_role_scope_and_domain_filters(
    tmp_path: Path,
):
    store = MemoryStore2(tmp_path / "memory2.db")
    engine = _make_default_engine(retriever=cast(Any, SimpleNamespace()))
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
    tmp_path: Path,
):
    store = MemoryStore2(tmp_path / "memory2.db")
    engine = _make_default_engine(retriever=cast(Any, SimpleNamespace()))
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
    tmp_path: Path,
):
    store = MemoryStore2(tmp_path / "memory2.db")
    engine = _make_default_engine(retriever=cast(Any, SimpleNamespace()))
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


async def test_default_memory_engine_consumes_markdown_consolidation_event():
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
    engine = _make_default_engine(
        provider=cast(Any, provider),
        memorizer=cast(Any, memorizer),
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


async def test_default_memory_engine_consolidation_role_scope_persists_role_id():
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
    engine = _make_default_engine(
        provider=cast(Any, provider),
        memorizer=cast(Any, memorizer),
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


async def test_default_memory_engine_reports_implicit_extraction_failure():
    memorizer = SimpleNamespace(
        save_from_consolidation=AsyncMock(),
        save_item_with_supersede=AsyncMock(return_value="new:memu-1"),
    )
    provider = SimpleNamespace(
        chat=AsyncMock(return_value=SimpleNamespace(content="not json"))
    )
    engine = _make_default_engine(
        provider=cast(Any, provider),
        memorizer=cast(Any, memorizer),
    )

    with pytest.raises(RuntimeError, match="long_term extraction failed"):
        await engine._on_consolidation_committed(
            ConsolidationCommitted(
                history_entry_payloads=[("[2026-03-15 10:00] 用户聊了 Zigbee", 6)],
                source_ref='["m1"]',
                scope_channel="cli",
                scope_chat_id="1",
                conversation="USER: 我买了 Zigbee 网关",
            )
        )

    memorizer.save_from_consolidation.assert_awaited_once()
    memorizer.save_item_with_supersede.assert_not_awaited()


async def test_default_memory_engine_ingest_accepts_conversation_batch_messages():
    worker = SimpleNamespace(run=AsyncMock())
    engine = _make_default_engine(
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


async def test_default_memory_engine_ingest_falls_back_to_post_response_source_ref():
    worker = SimpleNamespace(run=AsyncMock())
    engine = _make_default_engine(
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


async def test_default_memory_engine_ingest_rejects_unsupported_source_kind():
    worker = SimpleNamespace(run=AsyncMock())
    engine = _make_default_engine(
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


async def test_default_memory_engine_ingest_rejects_when_worker_missing():
    engine = _make_default_engine(
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


def test_default_memory_engine_descriptor_keeps_messages_capability_only():
    descriptor = DefaultMemoryEngine.DESCRIPTOR

    assert descriptor.profile == EngineProfile.RICH_MEMORY_ENGINE
    assert MemoryCapability.INGEST_MESSAGES in descriptor.capabilities
    assert MemoryCapability.INGEST_TEXT not in descriptor.capabilities


def test_build_memory_runtime_uses_memory_plugin(monkeypatch, tmp_path: Path):
    import bootstrap.memory as memory_module

    monkeypatch.setattr(
        memory_module,
        "register_memory_meta_tools",
        lambda *args, **kwargs: None,
    )

    captured: dict[str, object] = {}

    class _CustomEngine:
        def describe(self):
            return SimpleNamespace(name="custom")

    class _CustomPlugin:
        plugin_id = "custom"

        def build(self, deps):
            captured["deps"] = deps
            return MemoryPluginRuntime(engine=cast(Any, _CustomEngine()))

    monkeypatch.setattr(
        "bootstrap.wiring.resolve_memory_plugin",
        lambda name: _CustomPlugin(),
    )

    runtime = build_memory_runtime(
        config=Config(
            provider="test",
            model="gpt-test",
            api_key="k",
            system_prompt="hi",
            memory=MemoryConfig(enabled=True, engine="custom"),
        ),
        workspace=tmp_path,
        tools=ToolRegistry(),
        provider=cast(Any, SimpleNamespace()),
        light_provider=None,
        http_resources=cast(Any, SimpleNamespace(external_default=SimpleNamespace())),
    )

    assert runtime.engine is not None
    assert runtime.engine.describe().name == "custom"
    deps = captured["deps"]
    assert deps.config.model == "gpt-test"
    assert deps.workspace == tmp_path
    assert deps.http_resources is not None


def test_build_memory_runtime_exposes_default_memory_engine(
    monkeypatch,
    tmp_path: Path,
):
    import bootstrap.memory as memory_module

    monkeypatch.setattr(
        memory_module,
        "register_memory_meta_tools",
        lambda *args, **kwargs: None,
    )

    class _MemoryStore:
        def __init__(self, workspace):
            self.workspace = workspace

    class _SkillsLoader:
        def __init__(self, workspace):
            self.workspace = workspace

        def list_skills(self, filter_unavailable=False):
            return [{"name": "demo"}]

    class _WriteFileTool:
        pass

    class _EditFileTool:
        pass

    class _MemorizeTool:
        def __init__(self, engine):
            self.engine = engine

    class _Store2:
        def __init__(self, db_path):
            self.db_path = db_path

        def close(self):
            return None

    class _Embedder:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def close(self):
            return None

    class _Memorizer:
        def __init__(self, store, embedder):
            self.store = store
            self.embedder = embedder

    class _Retriever:
        def __init__(self, store, embedder, **kwargs):
            self.store = store
            self.embedder = embedder
            self.kwargs = kwargs

    class _ProcedureTagger:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    class _PostResponseMemoryWorker:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    monkeypatch.setattr("agent.memory.MemoryStore", _MemoryStore)
    monkeypatch.setattr("agent.skills.SkillsLoader", _SkillsLoader)
    monkeypatch.setattr("agent.tools.memorize.MemorizeTool", _MemorizeTool)
    monkeypatch.setattr("agent.tools.filesystem.WriteFileTool", _WriteFileTool)
    monkeypatch.setattr("agent.tools.filesystem.EditFileTool", _EditFileTool)
    monkeypatch.setattr("memory2.store.MemoryStore2", _Store2)
    monkeypatch.setattr("memory2.embedder.Embedder", _Embedder)
    monkeypatch.setattr("memory2.memorizer.Memorizer", _Memorizer)
    monkeypatch.setattr("memory2.retriever.Retriever", _Retriever)
    monkeypatch.setattr("memory2.procedure_tagger.ProcedureTagger", _ProcedureTagger)

    runtime = build_memory_runtime(
        config=Config(
            provider="test",
            model="gpt-test",
            api_key="k",
            system_prompt="hi",
            memory=MemoryConfig(enabled=True),
        ),
        workspace=tmp_path,
        tools=ToolRegistry(),
        provider=cast(Any, SimpleNamespace()),
        light_provider=None,
        http_resources=cast(Any, SimpleNamespace(external_default=SimpleNamespace())),
    )

    assert runtime.engine is not None
    assert runtime.engine.describe().name == "default"
    assert (
        MemoryCapability.SEMANTICS_RICH_MEMORY in runtime.engine.describe().capabilities
    )
