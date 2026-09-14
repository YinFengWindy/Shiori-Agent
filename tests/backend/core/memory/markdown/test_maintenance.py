"""Real Markdown commits stay consistent with concurrent Session undo."""

import asyncio
import threading
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

from agent.provider import LLMProvider
from agent.looping.core import AgentLoop
import agent.looping.core as loop_core
from agent.looping.ports import SessionServices
from bus.event_bus import EventBus
from core.memory.events import ConsolidationCommitted
from core.memory.markdown import (
    ConsolidateRequest,
    MarkdownMemoryMaintenance,
    MarkdownMemoryStore,
    MarkdownMemoryRuntime,
    MemoryLifecycleBindRequest,
)
from core.memory.markdown.contracts import _ConsolidationDraft
from core.memory.markdown.formatting import (
    _build_consolidation_source_ref,
    _select_consolidation_window,
)
from memory2.store import MemoryStore2
from plugins.default_memory.backend.engine import DefaultMemoryEngine
from plugins.plugin_undo.backend.plugin import PluginUndo
from session.manager import Session, SessionManager


def _setup(tmp_path: Path):
    manager = SessionManager(tmp_path)
    session = manager.get_or_create("role:mira")
    session.metadata["role_id"] = "mira"
    for index in range(3):
        session.add_message("user", f"question {index}")
        session.add_message("assistant", f"answer {index}")
    manager.save(session)
    event_bus = EventBus()
    maintenance = MarkdownMemoryMaintenance(
        store=MarkdownMemoryStore(tmp_path),
        provider=cast(LLMProvider, SimpleNamespace()),
        model="test",
        keep_count=0,
        event_bus=event_bus,
    )
    maintenance.bind_lifecycle(
        MemoryLifecycleBindRequest(
            get_session=manager.get_or_create,
            commit_consolidation=manager.commit_consolidation,
        )
    )
    return manager, session, maintenance, event_bus


def _draft(session: Session, *, archive_all: bool = False):
    window = _select_consolidation_window(
        session,
        keep_count=0,
        consolidation_min_new_messages=5,
        archive_all=archive_all,
        force=True,
    )
    assert window is not None
    return _ConsolidationDraft(
        window=window,
        source_ref=_build_consolidation_source_ref(window),
        history_entry_payloads=[("[2026-09-11 12:00] 你完成了第三轮问题。", 0)],
        pending_items="- [preference] 你喜欢第三轮讨论。",
        conversation="USER: question 2\nASSISTANT: answer 2",
        recent_context_text="# 最近发生的事\n\n第三轮讨论",
        scope_channel="desktop",
        scope_chat_id=session.key,
        archive_all=archive_all,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("background", [False, True])
async def test_prepared_draft_is_rejected_before_markdown_or_memory_writes_after_undo(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, background: bool
):
    manager, session, maintenance, event_bus = _setup(tmp_path)
    target = MarkdownMemoryStore(tmp_path / "roles" / "mira")
    before_files = {
        path: path.read_bytes()
        for path in target.memory_dir.rglob("*")
        if path.is_file()
    }
    events: list[ConsolidationCommitted] = []
    event_bus.on(ConsolidationCommitted, lambda event: events.append(event))
    prepared, resume = asyncio.Event(), asyncio.Event()

    async def prepare(source: Session, **_kwargs: Any):
        draft = _draft(source)
        assert draft.window.consolidate_up_to == 6
        prepared.set()
        await resume.wait()
        return draft

    monkeypatch.setattr(maintenance._worker, "prepare_consolidation", prepare)
    if background:
        maintenance.request_background_consolidation(session.key)
        task = asyncio.create_task(maintenance.drain())
    else:
        task = asyncio.create_task(
            maintenance.consolidate(ConsolidateRequest(session=session, force=True))
        )
    try:
        await asyncio.wait_for(prepared.wait(), timeout=2)
        assert "已撤销上一轮对话" in await PluginUndo(manager, None).undo(session.key)
        resume.set()
        result = await asyncio.wait_for(task, timeout=2)
        after_files = {
            path: path.read_bytes()
            for path in target.memory_dir.rglob("*")
            if path.is_file()
        }
        if not background:
            assert after_files == before_files
        assert len(session.messages) == 4
        assert session.last_consolidated == 0
        assert events == []
        assert after_files == before_files
        if not background:
            assert result.trace == {"mode": "skipped", "reason": "stale"}
        manager.invalidate(session.key)
        reloaded = manager.get_or_create(session.key)
        assert len(reloaded.messages) == 4
        assert reloaded.last_consolidated == 0
    finally:
        resume.set()
        await asyncio.gather(task, return_exceptions=True)
        await event_bus.aclose()


@pytest.mark.asyncio
async def test_undo_waits_for_started_commit_and_cleans_its_real_memory_sources(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    manager, session, maintenance, event_bus = _setup(tmp_path)
    memory_store = MemoryStore2(tmp_path / "memory2.db")
    memory_engine = DefaultMemoryEngine.__new__(DefaultMemoryEngine)
    memory_engine._v2_store = memory_store
    entered, resume = asyncio.Event(), asyncio.Event()
    item_ids: list[str] = []

    async def prepare(source: Session, **_kwargs: Any):
        return _draft(source)

    async def save_structured_memory(event: ConsolidationCommitted):
        # Markdown is already written. The awaited event consumer still owns commit.
        entered.set()
        await resume.wait()
        result = memory_store.upsert_item(
            memory_type="event",
            summary="第三轮讨论",
            embedding=[0.1, 0.2],
            source_ref=event.source_ref,
        )
        item_ids.append(result.split(":", 1)[1])

    monkeypatch.setattr(maintenance._worker, "prepare_consolidation", prepare)
    event_bus.on(ConsolidationCommitted, save_structured_memory)
    commit_task = asyncio.create_task(
        maintenance.consolidate(ConsolidateRequest(session=session, force=True))
    )
    undo_task = None
    try:
        await asyncio.wait_for(entered.wait(), timeout=2)
        undo_task = asyncio.create_task(
            PluginUndo(manager, memory_engine).undo(session.key)
        )
        await asyncio.sleep(0)
        assert not undo_task.done()
        assert len(session.messages) == 6
        resume.set()
        result, reply = await asyncio.wait_for(
            asyncio.gather(commit_task, undo_task), timeout=2
        )
        assert result.trace["mode"] == "markdown"
        assert "失效记忆：1 条" in reply
        assert memory_store.get_items_by_ids(item_ids)[0]["status"] == "superseded"
        assert len(session.messages) == 4
        assert session.last_consolidated == 0
        manager.invalidate(session.key)
        assert manager.get_or_create(session.key).last_consolidated == 0
    finally:
        resume.set()
        await asyncio.gather(
            commit_task, *([undo_task] if undo_task else []), return_exceptions=True
        )
        memory_store.close()
        await event_bus.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize("archive_all", [False, True])
async def test_successful_consolidation_persists_cursor_without_caller_save(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, archive_all: bool
):
    manager, session, maintenance, event_bus = _setup(tmp_path)
    session.last_consolidated = 2
    manager.save(session)

    async def prepare(source: Session, **_kwargs: Any):
        assert _kwargs["archive_all"] is archive_all
        assert _kwargs["force"] is True
        return _draft(source, archive_all=archive_all)

    monkeypatch.setattr(maintenance._worker, "prepare_consolidation", prepare)
    try:
        # Exercise the actual manual entrypoint, including force/archive_all routing.
        loop = AgentLoop.__new__(AgentLoop)
        loop._session_services = SessionServices(session_manager=manager)
        loop._markdown_memory = MarkdownMemoryRuntime(
            store=maintenance._store, maintenance=maintenance, workspace=tmp_path
        )
        assert (
            await loop.trigger_memory_consolidation(
                session.key, force=True, archive_all=archive_all
            )
            is True
        )
        manager.invalidate(session.key)
        reloaded = manager.get_or_create(session.key)
        assert len(reloaded.messages) == 6
        assert reloaded.last_consolidated == (0 if archive_all else 6)
    finally:
        await event_bus.aclose()


@pytest.mark.asyncio
async def test_manual_timeout_keeps_lock_until_threaded_markdown_commit_finishes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    manager, session, maintenance, event_bus = _setup(tmp_path)
    entered, finished = asyncio.Event(), asyncio.Event()
    release = threading.Event()
    event_loop = asyncio.get_running_loop()
    maintenance_task: asyncio.Task[Any] | None = None
    memory_store = MemoryStore2(tmp_path / "memory2.db")
    engine = DefaultMemoryEngine.__new__(DefaultMemoryEngine)
    engine._v2_store = memory_store
    item_ids: list[str] = []
    original_append = MarkdownMemoryStore.append_history_once

    def delayed_append(
        store: MarkdownMemoryStore,
        entry: str,
        *,
        source_ref: str,
        kind: str = "history_entry",
    ):
        event_loop.call_soon_threadsafe(entered.set)
        if not release.wait(timeout=5):
            raise TimeoutError("test did not release Markdown writer")
        result = original_append(store, entry, source_ref=source_ref, kind=kind)
        event_loop.call_soon_threadsafe(finished.set)
        return result

    async def prepare(source: Session, **_kwargs: Any):
        nonlocal maintenance_task
        maintenance_task = asyncio.current_task()
        return _draft(source)

    def save_source(event: ConsolidationCommitted):
        result = memory_store.upsert_item(
            memory_type="event",
            summary="committed memory",
            embedding=[0.1, 0.2],
            source_ref=event.source_ref,
        )
        item_ids.append(result.split(":", 1)[1])

    async def wait_for_cancellation():
        assert maintenance_task is not None
        while not maintenance_task.cancelling():
            await asyncio.sleep(0)

    monkeypatch.setattr(MarkdownMemoryStore, "append_history_once", delayed_append)
    monkeypatch.setattr(maintenance._worker, "prepare_consolidation", prepare)
    monkeypatch.setattr(loop_core, "_MANUAL_CONSOLIDATION_TIMEOUT_SECONDS", 0.05)
    event_bus.on(ConsolidationCommitted, save_source)
    loop = AgentLoop.__new__(AgentLoop)
    loop._session_services = SessionServices(session_manager=manager)
    loop._markdown_memory = MarkdownMemoryRuntime(
        store=maintenance._store, maintenance=maintenance, workspace=tmp_path
    )
    task = asyncio.create_task(
        loop.trigger_memory_consolidation(session.key, force=True)
    )
    undo_task = None
    try:
        await asyncio.wait_for(entered.wait(), timeout=2)
        # The real AgentLoop wait_for has cancelled maintenance while its thread writes.
        await asyncio.wait_for(wait_for_cancellation(), timeout=2)
        undo_task = asyncio.create_task(PluginUndo(manager, engine).undo(session.key))
        for _ in range(5):
            await asyncio.sleep(0)
        assert not undo_task.done()
        assert not task.done()
        assert len(session.messages) == 6
        release.set()
        outcome, reply = await asyncio.wait_for(
            asyncio.gather(task, undo_task, return_exceptions=True), timeout=2
        )
        assert isinstance(outcome, TimeoutError)
        assert "memory consolidation busy" in str(outcome)
        assert finished.is_set()
        assert isinstance(reply, str)
        assert "失效记忆：1 条" in reply
        assert memory_store.get_items_by_ids(item_ids)[0]["status"] == "superseded"
        assert len(session.messages) == 4
        assert session.last_consolidated == 0
        manager.invalidate(session.key)
        assert manager.get_or_create(session.key).last_consolidated == 0
    finally:
        release.set()
        await asyncio.gather(
            task, *([undo_task] if undo_task else []), return_exceptions=True
        )
        await asyncio.wait_for(finished.wait(), timeout=2)
        memory_store.close()
        await event_bus.aclose()


@pytest.mark.asyncio
async def test_ensure_consolidation_runs_non_force_then_force_when_budget_remains(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    manager, session, maintenance, event_bus = _setup(tmp_path)
    calls: list[bool] = []
    budget_states = iter((True, True, False))

    async def consolidate(request: ConsolidateRequest):
        calls.append(request.force)
        return SimpleNamespace(trace={"mode": "markdown"})

    monkeypatch.setattr(maintenance, "consolidate", consolidate)
    monkeypatch.setattr(
        "core.memory.markdown.maintenance._session_input_over_budget",
        lambda *_args, **_kwargs: next(budget_states),
    )
    try:
        assert await maintenance.ensure_consolidation(session.key) is True
        assert calls == [False, True]
    finally:
        await event_bus.aclose()


@pytest.mark.asyncio
async def test_ensure_consolidation_returns_false_when_no_progress(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    _manager, session, maintenance, event_bus = _setup(tmp_path)

    async def consolidate(_request: ConsolidateRequest):
        return SimpleNamespace(trace={"mode": "skipped"})

    monkeypatch.setattr(maintenance, "consolidate", consolidate)
    monkeypatch.setattr(
        "core.memory.markdown.maintenance._session_input_over_budget",
        lambda *_args, **_kwargs: True,
    )
    try:
        assert await maintenance.ensure_consolidation(session.key) is False
    finally:
        await event_bus.aclose()


@pytest.mark.asyncio
async def test_ensure_consolidation_propagates_existing_background_failure(
    tmp_path: Path,
):
    _manager, session, maintenance, event_bus = _setup(tmp_path)

    started, release = asyncio.Event(), asyncio.Event()

    async def fail():
        started.set()
        await release.wait()
        raise RuntimeError("provider failed")

    maintenance._maintenance_tasks[session.key] = asyncio.create_task(fail())
    try:
        await started.wait()
        pending = asyncio.create_task(maintenance.ensure_consolidation(session.key))
        await asyncio.sleep(0)
        release.set()
        with pytest.raises(RuntimeError, match="provider failed"):
            await pending
    finally:
        await event_bus.aclose()


@pytest.mark.asyncio
async def test_concurrent_ensure_consolidation_shares_in_flight_task(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    _manager, session, maintenance, event_bus = _setup(tmp_path)
    entered, release = asyncio.Event(), asyncio.Event()
    calls = 0

    async def ensure_impl(_session_key: str, _current_content: str):
        nonlocal calls
        calls += 1
        entered.set()
        await release.wait()
        return True

    monkeypatch.setattr(maintenance, "_ensure_consolidation", ensure_impl)
    first = asyncio.create_task(maintenance.ensure_consolidation(session.key))
    await entered.wait()
    second = asyncio.create_task(maintenance.ensure_consolidation(session.key))
    release.set()
    try:
        assert await asyncio.gather(first, second) == [True, True]
        assert calls == 1
    finally:
        await event_bus.aclose()
