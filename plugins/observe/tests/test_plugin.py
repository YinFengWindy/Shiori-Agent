"""Observe setup, event translation and resource rollback using only SDK ports."""

from __future__ import annotations
import asyncio
import json
import logging
import sqlite3
from contextlib import closing, asynccontextmanager
from pathlib import Path
from typing import Any
import pytest
from plugins.observe.backend.plugin import setup
from shiori_sdk.memory.committed import TurnCommitted
from shiori_sdk.memory.events import (
    MemoryWritten,
    RetrievalCompleted,
    RetrievalHitSummary,
)
from shiori_sdk.testing.extensions import FakeExtensionContext


@asynccontextmanager
async def _loaded(workspace):
    ctx = FakeExtensionContext("observe", workspace=workspace)
    try:
        await setup(ctx)
        yield ctx, ctx.events
    finally:
        await ctx.aclose()


@pytest.fixture
def opened_connections(monkeypatch: pytest.MonkeyPatch):
    """Track real SQLite connections so lifecycle tests can verify closure."""
    opened: list[sqlite3.Connection] = []
    connect = sqlite3.connect

    def track_connection(*args: Any, **kwargs: Any):
        conn = connect(*args, **kwargs)
        opened.append(conn)
        return conn

    monkeypatch.setattr(sqlite3, "connect", track_connection)
    return opened


def _assert_connections_closed(opened: list[sqlite3.Connection]) -> None:
    for conn in opened:
        with pytest.raises(sqlite3.ProgrammingError, match="closed"):
            _ = conn.execute("SELECT 1")


def _turn_committed(**overrides: object) -> TurnCommitted:
    defaults: dict[str, object] = dict(
        session_key="cli:1",
        channel="cli",
        chat_id="1",
        input_message="hi",
        persisted_user_message="hi",
        assistant_response="hello",
        tools_used=[],
    )
    defaults.update(overrides)
    return TurnCommitted(**defaults)


def _retrieval_completed(**overrides: object) -> RetrievalCompleted:
    defaults: dict[str, object] = dict(
        session_key="cli:1",
        channel="cli",
        chat_id="1",
        query="改写问题",
        orig_query="原始问题",
        hits=[
            RetrievalHitSummary(
                item_id="mem_1",
                memory_type="event",
                # summary 故意超过 120 字符，证明 _to_rag_query_log 的截断逻辑真的跑了，
                # 而不只是原样透传。
                score=0.9,
                summary="命中的记忆" * 30,
                injected=True,
            )
        ],
        injected_count=1,
        route_decision="RETRIEVE",
        aux_queries=["假想问题"],
    )
    defaults.update(overrides)
    return RetrievalCompleted(**defaults)


def _memory_written(**overrides: object) -> MemoryWritten:
    defaults: dict[str, object] = dict(
        session_key="cli:1",
        channel="cli",
        chat_id="1",
        action="supersede",
        source_ref="cli:1@post_response",
        superseded_ids=["mem_1"],
    )
    defaults.update(overrides)
    return MemoryWritten(**defaults)


async def _wait_for_turn_row(db_path: Path, *, timeout: float = 5.0) -> int:
    """Polls observe.db until the async writer task has committed a row."""
    return await _wait_for_table_count(db_path, "turns", timeout=timeout)


async def _wait_for_table_count(
    db_path: Path, table: str, *, timeout: float = 5.0
) -> int:
    """Polls observe.db until the async writer task has committed a row into ``table``."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        if db_path.exists():
            with closing(sqlite3.connect(str(db_path))) as conn:
                count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                if count:
                    return int(count)
        await asyncio.sleep(0.02)
    return 0


@pytest.mark.asyncio
async def test_turn_committed_event_reaches_writer_and_is_persisted(
    tmp_path: Path,
) -> None:
    """setup() 必须与旧 ObservePlugin.initialize() 等价：TurnCommitted 经事件订阅
    真正写入 observe.db（而不仅仅是"没抛异常"）。"""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    async with _loaded(workspace) as (ctx, bus):

        _ = await bus.emit(_turn_committed())

        db_path = workspace / "plugin-data" / "observe" / "observe.db"
        row_count = await _wait_for_turn_row(db_path)
        assert row_count == 1


@pytest.mark.asyncio
async def test_retrieval_completed_event_translated_and_persisted(
    tmp_path: Path,
) -> None:
    """RetrievalCompleted 订阅必须真正落库，且经 _to_rag_query_log 翻译
    （截断 summary 到 120 字符、映射 hits_json）——不是只订阅了事件却没接对
    翻译函数。"""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    async with _loaded(workspace) as (ctx, bus):

        db_path = workspace / "plugin-data" / "observe" / "observe.db"
        _ = await bus.emit(_retrieval_completed())
        row_count = await _wait_for_table_count(db_path, "rag_queries")
        assert row_count == 1

        with closing(sqlite3.connect(str(db_path))) as conn:
            row = conn.execute(
                """SELECT caller, session_key, query, orig_query, aux_queries,
                          hits_json, injected_count, route_decision, error
                   FROM rag_queries"""
            ).fetchone()

        (
            caller,
            session_key,
            query,
            orig_query,
            aux_queries_json,
            hits_json,
            injected_count,
            route_decision,
            error,
        ) = row
        assert caller == "passive"
        assert session_key == "cli:1"
        assert query == "改写问题"
        assert orig_query == "原始问题"
        assert json.loads(aux_queries_json) == ["假想问题"]
        assert injected_count == 1
        assert route_decision == "RETRIEVE"
        assert error is None

        hits = json.loads(hits_json)
        assert len(hits) == 1
        # 翻译函数把 summary 截到 120 字符（RagHitLog 构造时做的），源 summary 是
        # "命中的记忆" * 30 = 150 字符；证明截断逻辑真的跑了，而不是原样透传。
        assert hits[0]["id"] == "mem_1"
        assert hits[0]["type"] == "event"
        assert hits[0]["score"] == 0.9
        assert hits[0]["injected"] is True
        assert len(hits[0]["summary"]) == 120
        assert hits[0]["summary"] == ("命中的记忆" * 30)[:120]


@pytest.mark.asyncio
async def test_memory_written_event_translated_and_persisted(tmp_path: Path) -> None:
    """MemoryWritten 订阅必须真正落库，且经 _to_memory_write_trace 翻译
    （action/source_ref/superseded_ids 映射到对应列）。"""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    async with _loaded(workspace) as (ctx, bus):

        db_path = workspace / "plugin-data" / "observe" / "observe.db"
        _ = await bus.emit(_memory_written())
        row_count = await _wait_for_table_count(db_path, "memory_writes")
        assert row_count == 1

        with closing(sqlite3.connect(str(db_path))) as conn:
            row = conn.execute(
                """SELECT session_key, source_ref, action, memory_type, item_id,
                          summary, superseded_ids, error
                   FROM memory_writes"""
            ).fetchone()

        (
            session_key,
            source_ref,
            action,
            memory_type,
            item_id,
            summary,
            superseded_ids_json,
            error,
        ) = row
        assert session_key == "cli:1"
        assert source_ref == "cli:1@post_response"
        assert action == "supersede"
        assert memory_type is None
        assert item_id is None
        assert summary is None
        assert json.loads(superseded_ids_json) == ["mem_1"]
        assert error is None


@pytest.mark.asyncio
async def test_setup_skips_without_workspace():
    async with _loaded(None) as (ctx, _):
        assert ctx.exported is None
        assert not ctx.diagnostics.owners


@pytest.mark.asyncio
@pytest.mark.parametrize("cancel", [False, True])
async def test_partial_collector_install_is_rolled_back(
    tmp_path, monkeypatch, cancel, opened_connections
):
    ctx = FakeExtensionContext("observe", workspace=tmp_path)
    install = ctx.diagnostics.install_global_hooks

    def fail_install(*args, **kwargs):
        install(*args, **kwargs)
        if cancel:
            raise asyncio.CancelledError("collector install cancelled")
        raise RuntimeError("collector install failed")

    monkeypatch.setattr(ctx.diagnostics, "install_global_hooks", fail_install)
    with pytest.raises(asyncio.CancelledError if cancel else RuntimeError):
        try:
            await setup(ctx)
        finally:
            await ctx.aclose()
    assert not ctx.diagnostics.owners
    assert not ctx._events._subscriptions
    _assert_connections_closed(opened_connections)


@pytest.mark.asyncio
async def test_cancel_setup_during_readiness_closes_started_writer(
    tmp_path, monkeypatch, opened_connections
):
    ctx = FakeExtensionContext("observe", workspace=tmp_path)
    spawn = ctx.background.spawn

    def cancel_after_spawn(coro, *, name):
        task = spawn(coro, name=name)
        if name == "writer":
            current = asyncio.current_task()
            assert current is not None
            asyncio.get_running_loop().call_soon(current.cancel)
        return task

    monkeypatch.setattr(ctx.background, "spawn", cancel_after_spawn)

    async def load():
        try:
            await setup(ctx)
        finally:
            await ctx.aclose()

    with pytest.raises(asyncio.CancelledError):
        await asyncio.create_task(load())
    assert not ctx.diagnostics.owners
    assert not ctx._events._subscriptions
    _assert_connections_closed(opened_connections)


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["path_collision", "schema"])
async def test_initialization_failure_rolls_back_and_can_reload(
    tmp_path, failure, opened_connections
):
    db_path = tmp_path / "plugin-data/observe/observe.db"
    db_path.parent.parent.mkdir(parents=True)
    if failure == "path_collision":
        db_path.parent.write_text("occupied", encoding="utf-8")
    else:
        db_path.parent.mkdir()
        with closing(sqlite3.connect(db_path)) as conn:
            conn.execute("CREATE TABLE turns (id INTEGER)")
    with pytest.raises((FileExistsError, sqlite3.OperationalError)):
        async with _loaded(tmp_path):
            pass
    _assert_connections_closed(opened_connections)
    if failure == "path_collision":
        db_path.parent.unlink()
    else:
        db_path.unlink()
    async with _loaded(tmp_path) as (ctx, bus):
        await bus.emit(_turn_committed())
        assert await _wait_for_turn_row(db_path) == 1
    _assert_connections_closed(opened_connections)


@pytest.mark.asyncio
async def test_setup_failure_after_registration_cleans_all_resources(
    tmp_path, monkeypatch, opened_connections
):
    def fail_expose(self, api):
        raise RuntimeError("expose failed after subscriptions")

    monkeypatch.setattr(FakeExtensionContext, "expose", fail_expose)
    ctx = FakeExtensionContext("observe", workspace=tmp_path)
    with pytest.raises(RuntimeError, match="expose failed"):
        try:
            await setup(ctx)
        finally:
            await ctx.aclose()
    assert not ctx.diagnostics.owners
    assert not ctx._events._subscriptions
    _assert_connections_closed(opened_connections)


@pytest.mark.asyncio
async def test_unload_flushes_final_errors_and_stops_observations(
    tmp_path, opened_connections
):
    db_path = tmp_path / "plugin-data/observe/observe.db"
    async with _loaded(tmp_path) as (ctx, bus):
        assert db_path.exists()
        await bus.emit(_turn_committed())
        assert await _wait_for_turn_row(db_path) == 1
        assert ctx.diagnostics.handler is not None
        ctx.diagnostics.handler.emit(
            logging.LogRecord(
                "test.final_flush",
                logging.ERROR,
                __file__,
                1,
                "last collected error",
                (),
                None,
            )
        )
    await bus.emit(_turn_committed(session_key="cli:2"))
    with closing(sqlite3.connect(db_path)) as conn:
        assert conn.execute("SELECT COUNT(*) FROM turns").fetchone()[0] == 1
        assert conn.execute(
            "SELECT message FROM global_errors WHERE logger_name='test.final_flush'"
        ).fetchone() == ("last collected error",)
    assert not ctx.diagnostics.owners
    _assert_connections_closed(opened_connections)


@pytest.mark.asyncio
async def test_writer_and_public_reader_use_the_storage_owners_resolved_database(
    tmp_path,
):
    from plugins.observe.backend.storage import database_path
    from plugins.observe.backend.telemetry import ObserveTelemetry
    from shiori_sdk.testing.memory import FakeMemoryStorage

    workspace = tmp_path / "workspace"
    destination = tmp_path / "relocated-private-data"

    class Storage(FakeMemoryStorage):
        def migrate_data(self, workspace, plugin_id, name, source):
            return destination / name

    ctx = FakeExtensionContext("observe", workspace=workspace)
    ctx.storage = Storage()
    try:
        await setup(ctx)
        reader = ctx.exported
        assert isinstance(reader, ObserveTelemetry)
        await ctx.events.emit(
            _turn_committed(
                assistant_response="stored at the owner-selected path",
                react_stats={"cache_prompt_tokens": 100, "cache_hit_tokens": 75},
            )
        )
        async with asyncio.timeout(5):
            while not (turns := reader.recent_cache_turns("cli:1")):
                await asyncio.sleep(0.01)
        assert turns[0].reply == "stored at the owner-selected path"
        assert (turns[0].prompt_tokens, turns[0].hit_tokens) == (100, 75)
        assert (destination / "observe.db").is_file()
        assert not database_path(workspace).exists()
    finally:
        await ctx.aclose()
    assert (destination / ".last_cleanup").is_file()


async def test_context_budget_sdk_event_is_observed_without_a_committed_turn(tmp_path):
    from shiori_sdk.context import ContextBudgetObserved

    ctx = FakeExtensionContext("observe", workspace=tmp_path)
    try:
        await setup(ctx)
        await ctx.events.emit(
            ContextBudgetObserved(
                "role:mira",
                "user",
                {
                    "reason": "manual",
                    "failure_stage": "summary",
                    "memory_committed": True,
                },
            )
        )
        async with asyncio.timeout(5):
            while not (
                records := ctx.exported.recent_context_budgets("role:mira", "user")
            ):
                await asyncio.sleep(0.01)
        assert records[0]["status"]["memory_committed"]
        assert records[0]["status"]["failure_stage"] == "summary"
    finally:
        await ctx.aclose()
