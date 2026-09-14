from __future__ import annotations

import asyncio
import json
import logging
import sqlite3
import sys
import threading
from contextlib import closing
from pathlib import Path
from typing import Any

import pytest
from shiori_plugin_testkit.packages import stage_plugin_package

from agent.plugin_host import HostServices, PluginKernel
from agent.plugin_host.capabilities import BackgroundCapability
from agent.plugin_host.runtime_context import PluginRuntimeContext
from bus.event_bus import EventBus
from bus.events_lifecycle import TurnCommitted
from core.memory.events import MemoryWritten, RetrievalCompleted, RetrievalHitSummary
from core.common import global_hook_stack

PLUGIN_DIR = Path(__file__).resolve().parents[1]


def _global_hooks():
    return (
        sys.excepthook,
        threading.excepthook,
        asyncio.get_running_loop().get_exception_handler(),
        tuple(logging.getLogger().handlers),
    )


def _observe_tasks():
    return {
        task
        for task in asyncio.all_tasks()
        if task.get_name().startswith(("plugin:observe:", "observe_error_flush"))
    }


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


@pytest.mark.asyncio
@pytest.mark.parametrize("cancel", [False, True])
async def test_partial_collector_install_is_rolled_back(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    cancel: bool,
    opened_connections: list[sqlite3.Connection],
) -> None:
    kernel, bus = _load_observe_kernel(tmp_path, workspace=tmp_path / "workspace")
    hooks = _global_hooks()
    tasks = _observe_tasks()
    install = global_hook_stack.install_global_hooks

    def fail_install(*args: Any, **kwargs: Any):
        _ = install(*args, **kwargs)
        if cancel:
            raise asyncio.CancelledError("collector install cancelled")
        raise RuntimeError("collector install failed")

    monkeypatch.setattr(global_hook_stack, "install_global_hooks", fail_install)
    try:
        if cancel:
            with pytest.raises(asyncio.CancelledError, match="install cancelled"):
                _ = await kernel.load("observe")
        else:
            assert await kernel.load("observe") is False
            assert "collector install failed" in kernel.states()[0]["error"]
        assert kernel.states()[0]["state"] == "FAILED"
        assert _global_hooks() == hooks
        assert _observe_tasks() == tasks
        assert not bus._handlers
        assert opened_connections
        _assert_connections_closed(opened_connections)
    finally:
        await kernel.terminate_all()


@pytest.mark.asyncio
async def test_cancel_setup_during_readiness_closes_started_writer(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    opened_connections: list[sqlite3.Connection],
) -> None:
    kernel, bus = _load_observe_kernel(tmp_path, workspace=tmp_path / "workspace")
    hooks = _global_hooks()
    tasks = _observe_tasks()
    spawn = BackgroundCapability.spawn

    def cancel_after_spawn(self: BackgroundCapability, coro: Any, *, name: str):
        task = spawn(self, coro, name=name)
        if name == "writer":
            setup_task = asyncio.current_task()
            assert setup_task is not None
            _ = asyncio.get_running_loop().call_soon(setup_task.cancel)
        return task

    monkeypatch.setattr(BackgroundCapability, "spawn", cancel_after_spawn)
    try:
        with pytest.raises(asyncio.CancelledError):
            _ = await asyncio.create_task(kernel.load("observe"))
        assert kernel.states()[0]["state"] == "FAILED"
        assert _global_hooks() == hooks
        assert _observe_tasks() == tasks
        assert not bus._handlers
        assert len(opened_connections) == 1
        _assert_connections_closed(opened_connections)
    finally:
        await kernel.terminate_all()


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["path_collision", "schema"])
async def test_initialization_failure_rolls_back_and_can_reload(
    tmp_path: Path, failure: str, opened_connections: list[sqlite3.Connection]
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    db_path = workspace / "observe" / "observe.db"
    if failure == "path_collision":
        _ = db_path.parent.write_text("occupied", encoding="utf-8")
        expected_error = repr(str(db_path.parent))
    else:
        db_path.parent.mkdir()
        with closing(sqlite3.connect(db_path)) as conn:
            _ = conn.execute("CREATE TABLE turns (id INTEGER)")
        expected_error = "no such column: session_key"

    kernel, bus = _load_observe_kernel(tmp_path, workspace=workspace)
    healthy = tmp_path / "plugins" / "healthy"
    (healthy / "backend").mkdir(parents=True)
    _ = (healthy / "manifest.yaml").write_text(
        "api: 2\nid: healthy\ncapabilities: [events]\n", encoding="utf-8"
    )
    _ = (healthy / "backend" / "plugin.py").write_text(
        "from bus.events_lifecycle import TurnCommitted\n"
        "async def setup(ctx):\n"
        "    ctx.events.on(TurnCommitted, lambda event: None)\n",
        encoding="utf-8",
    )
    hooks = _global_hooks()
    tasks = _observe_tasks()
    try:
        await kernel.load_all()
        states = {entry["id"]: entry for entry in kernel.states()}
        assert states["observe"]["state"] == "FAILED"
        assert expected_error in states["observe"]["error"]
        assert states["healthy"]["state"] == "ACTIVE"
        assert _global_hooks() == hooks
        assert _observe_tasks() == tasks
        _assert_connections_closed(opened_connections)
        # The healthy plugin remains subscribed; observe leaves no subscriptions.
        assert len(bus._handlers[TurnCommitted]) == 1
        assert not bus._handlers.get(RetrievalCompleted)
        assert not bus._handlers.get(MemoryWritten)

        if failure == "path_collision":
            db_path.parent.unlink()
        else:
            db_path.unlink()
        assert await kernel.load("observe") is True
        assert db_path.exists()
        _ = await bus.emit(_turn_committed())
        assert await _wait_for_turn_row(db_path) == 1
    finally:
        await kernel.terminate_all()
    assert _global_hooks() == hooks
    assert _observe_tasks() == tasks
    _assert_connections_closed(opened_connections)


@pytest.mark.asyncio
async def test_setup_failure_after_registration_cleans_all_resources(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    opened_connections: list[sqlite3.Connection],
) -> None:
    kernel, bus = _load_observe_kernel(tmp_path, workspace=tmp_path / "workspace")
    hooks = _global_hooks()
    tasks = _observe_tasks()

    def fail_expose(self: PluginRuntimeContext, api: object) -> None:
        raise RuntimeError("expose failed after subscriptions")

    monkeypatch.setattr(PluginRuntimeContext, "expose", fail_expose)
    try:
        assert await kernel.load("observe") is False
        assert "expose failed after subscriptions" in kernel.states()[0]["error"]
        assert _global_hooks() == hooks
        assert _observe_tasks() == tasks
        assert not bus._handlers.get(TurnCommitted)
        assert not bus._handlers.get(RetrievalCompleted)
        assert not bus._handlers.get(MemoryWritten)
        assert opened_connections
        _assert_connections_closed(opened_connections)
    finally:
        await kernel.terminate_all()


@pytest.mark.asyncio
async def test_unload_persists_final_collector_flush(
    tmp_path: Path, opened_connections: list[sqlite3.Connection]
) -> None:
    workspace = tmp_path / "workspace"
    kernel, _ = _load_observe_kernel(tmp_path, workspace=workspace)
    hooks = _global_hooks()
    tasks = _observe_tasks()
    try:
        assert await kernel.load("observe")
        db_path = workspace / "observe" / "observe.db"
        assert db_path.exists(), "setup must wait for database readiness"
        logging.getLogger("test.final_flush").error("last collected error")
        assert await kernel.unload("observe") == []
        with closing(sqlite3.connect(db_path)) as conn:
            row = conn.execute(
                "SELECT message FROM global_errors WHERE logger_name = ?",
                ("test.final_flush",),
            ).fetchone()
        assert row == ("last collected error",)
        assert _global_hooks() == hooks
        assert _observe_tasks() == tasks
        _assert_connections_closed(opened_connections)
    finally:
        await kernel.terminate_all()


def _load_observe_kernel(
    tmp_path: Path, *, workspace: Path | None
) -> tuple[PluginKernel, EventBus]:
    root = tmp_path / "plugins"
    root.mkdir()
    stage_plugin_package(PLUGIN_DIR, root / "observe")
    bus = EventBus()
    kernel = PluginKernel(
        [root], services=HostServices(event_bus=bus, workspace=workspace)
    )
    return kernel, bus


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
async def test_setup_skips_without_workspace(tmp_path: Path) -> None:
    """workspace 缺失时插件仍加载成功但不贡献任何行为，对齐旧 initialize() 的早退。"""
    kernel, _bus = _load_observe_kernel(tmp_path, workspace=None)

    await kernel.load_all()

    assert kernel.loaded_count == 1
    _ = await kernel.terminate_all()


@pytest.mark.asyncio
async def test_turn_committed_event_reaches_writer_and_is_persisted(
    tmp_path: Path,
) -> None:
    """setup() 必须与旧 ObservePlugin.initialize() 等价：TurnCommitted 经事件订阅
    真正写入 observe.db（而不仅仅是"没抛异常"）。"""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    kernel, bus = _load_observe_kernel(tmp_path, workspace=workspace)
    await kernel.load_all()
    assert kernel.loaded_count == 1

    _ = await bus.emit(_turn_committed())

    db_path = workspace / "observe" / "observe.db"
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
    kernel, bus = _load_observe_kernel(tmp_path, workspace=workspace)
    await kernel.load_all()

    db_path = workspace / "observe" / "observe.db"
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
    kernel, bus = _load_observe_kernel(tmp_path, workspace=workspace)
    await kernel.load_all()

    db_path = workspace / "observe" / "observe.db"
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
async def test_unload_cancels_background_tasks_and_uninstalls_collector_cleanly(
    tmp_path: Path,
) -> None:
    """卸载必须干净收尾：不抛异常，且卸载后事件不再落库（effect 真正生效）。"""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    kernel, bus = _load_observe_kernel(tmp_path, workspace=workspace)
    await kernel.load_all()
    _ = await bus.emit(_turn_committed(session_key="cli:1"))
    db_path = workspace / "observe" / "observe.db"
    _ = await _wait_for_turn_row(db_path)

    errors = await kernel.unload("observe")
    assert errors == []

    # 卸载后订阅应已随 effect 撤销；再 emit 不应再增加行数
    row_count_before = await _wait_for_turn_row(db_path, timeout=0.2)
    _ = await bus.emit(_turn_committed(session_key="cli:2"))
    await asyncio.sleep(0.1)
    with closing(sqlite3.connect(str(db_path))) as conn:
        row_count_after = conn.execute("SELECT COUNT(*) FROM turns").fetchone()[0]
    assert row_count_after == row_count_before
