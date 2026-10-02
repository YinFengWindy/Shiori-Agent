from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from bus.event_bus import EventBus
from shiori_sdk.memory.committed import TurnCommitted
from shiori_sdk.memory.events import ConsolidationCommitted
from core.memory.markdown import (
    ConsolidateRequest,
    ConsolidateResult,
    ConsolidationFailure,
    ConsolidationWindow,
    MarkdownMemoryMaintenance,
    MarkdownMemoryStore,
    MemoryLifecycleBindRequest,
    _ConsolidationDraft,
)
from core.memory.markdown.contracts import ConsolidationSegments
from core.roles import RoleStore
from session.manager import Session, SessionManager


async def _drain_maintenance(maintenance: object) -> None:
    for _ in range(5):
        tasks = list(getattr(maintenance, "_maintenance_tasks").values())
        if not tasks:
            return
        await asyncio.gather(*tasks)
        await asyncio.sleep(0)


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
async def test_markdown_maintenance_records_background_consolidation_failure(
    tmp_path: Path,
):
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
        return_value=ConsolidationFailure(
            step="event",
            error="provider timeout",
            elapsed_ms=100,
        )
    )
    maintenance.bind_lifecycle(
        MemoryLifecycleBindRequest(
            get_session=lambda _key: session,
            commit_consolidation=AsyncMock(),
            group_environment=cast(Any, object()),
            runtime_roles=RoleStore(tmp_path),
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
            commit_consolidation=AsyncMock(),
            group_environment=cast(Any, object()),
            runtime_roles=RoleStore(tmp_path),
        )
    )

    maintenance.request_background_consolidation(session.key)
    await asyncio.wait_for(started.wait(), timeout=1)

    assert session.key in maintenance._maintenance_tasks
    release.set()
    await _drain_maintenance(maintenance)


async def test_default_memory_engine_refreshes_recent_context_from_lifecycle_role_only(
    tmp_path: Path,
):
    event_bus = EventBus()
    session = SimpleNamespace(
        key="role:mira",
        metadata={"role_id": "mira"},
        messages=[{"role": "user", "content": "u"}],
        last_consolidated=0,
    )
    maintenance = MarkdownMemoryMaintenance(
        store=MarkdownMemoryStore(tmp_path),
        provider=cast(Any, SimpleNamespace()),
        model="lm",
        keep_count=20,
        event_bus=event_bus,
    )
    maintenance.refresh_recent_turns = AsyncMock()
    commit_consolidation = AsyncMock()
    maintenance.bind_lifecycle(
        MemoryLifecycleBindRequest(
            get_session=lambda _key: session,
            commit_consolidation=commit_consolidation,
            group_environment=cast(Any, object()),
            runtime_roles=RoleStore(tmp_path),
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
    commit_consolidation.assert_not_awaited()
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
    commit_consolidation = AsyncMock()
    maintenance.bind_lifecycle(
        MemoryLifecycleBindRequest(
            get_session=lambda _key: session,
            commit_consolidation=commit_consolidation,
            group_environment=cast(Any, object()),
            runtime_roles=RoleStore(tmp_path),
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
    assert global_recent_context_path.exists()
    assert "# 最近发生的事" in global_recent_context_path.read_text(encoding="utf-8")
    commit_consolidation.assert_not_awaited()
    await event_bus.aclose()


async def test_default_memory_engine_consolidates_ready_session_from_lifecycle(
    tmp_path: Path,
):
    event_bus = EventBus()
    session = SimpleNamespace(
        key="role:mira",
        metadata={"role_id": "mira"},
        messages=[{"role": "user", "content": "u"}] * 31,
        last_consolidated=0,
    )
    maintenance = MarkdownMemoryMaintenance(
        store=MarkdownMemoryStore(tmp_path),
        provider=cast(Any, SimpleNamespace()),
        model="lm",
        keep_count=20,
        event_bus=event_bus,
    )
    maintenance._consolidate_unlocked = AsyncMock(
        return_value=ConsolidateResult(trace={"mode": "markdown"})
    )
    commit_consolidation = AsyncMock()
    maintenance.bind_lifecycle(
        MemoryLifecycleBindRequest(
            get_session=lambda _key: session,
            commit_consolidation=commit_consolidation,
            group_environment=cast(Any, object()),
            runtime_roles=RoleStore(tmp_path),
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
    commit_consolidation.assert_not_awaited()
    await event_bus.aclose()


async def test_markdown_consolidation_commits_memory_when_consumer_fails(
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
    manager = SessionManager(tmp_path)
    session = Session(
        key=session.key,
        metadata=session.metadata,
        messages=[dict(message) for message in session.messages],
    )
    manager.save(session)
    maintenance = MarkdownMemoryMaintenance(
        store=MarkdownMemoryStore(tmp_path),
        provider=cast(Any, SimpleNamespace()),
        model="lm",
        keep_count=6,
        event_bus=event_bus,
    )
    maintenance.bind_lifecycle(
        MemoryLifecycleBindRequest(
            get_session=manager.get_or_create,
            commit_consolidation=manager.commit_consolidation,
            retry_consumers=manager.retry_memory_consumers,
            record_publication=manager.record_memory_publication,
            record_recent_context=manager.record_recent_context,
            group_environment=cast(Any, object()),
            runtime_roles=RoleStore(tmp_path),
        )
    )
    draft = _ConsolidationDraft(
        window=ConsolidationWindow(
            old_messages=list(session.messages[:6]),
            keep_count=6,
            consolidate_up_to=6,
            scopes=("user",),
        ),
        segments=ConsolidationSegments(
            user_messages=list(session.messages[:6]), external_messages=[]
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

    result = await maintenance.consolidate(ConsolidateRequest(session=session))
    assert result.trace["memory_committed"] is True
    assert result.trace["step"] == "consumers"
    assert "vector write failed" in str(result.trace["error"])

    assert session.context_cursors == {"user": 6, "external": 0}
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
    maintenance.bind_lifecycle(
        MemoryLifecycleBindRequest(
            get_session=lambda _key: session,
            commit_consolidation=AsyncMock(),
            group_environment=cast(Any, object()),
            runtime_roles=RoleStore(tmp_path),
        )
    )
    maintenance._worker.prepare_consolidation = AsyncMock(
        return_value=ConsolidationFailure(
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
    manager = SessionManager(tmp_path)
    session = Session(
        key=session.key,
        metadata=session.metadata,
        messages=[dict(message) for message in session.messages],
    )
    manager.save(session)
    maintenance = MarkdownMemoryMaintenance(
        store=MarkdownMemoryStore(tmp_path),
        provider=cast(Any, SimpleNamespace()),
        model="lm",
        keep_count=6,
    )
    draft = _ConsolidationDraft(
        window=ConsolidationWindow(
            old_messages=list(session.messages[:6]),
            keep_count=6,
            consolidate_up_to=6,
            scopes=("user",),
        ),
        segments=ConsolidationSegments(
            user_messages=list(session.messages[:6]), external_messages=[]
        ),
        source_ref='["role:mira:0"]',
        history_entry_payloads=[],
        pending_items="",
        conversation="USER: hi",
        recent_context_text="# Recent Context\n",
        scope_channel="desktop",
        scope_chat_id="role:mira",
    )
    # 角色会话每类上下文各试一个窗口；只有用户上下文这一窗有内容。
    maintenance._worker.prepare_consolidation = AsyncMock(side_effect=[draft, None])
    after_consolidation = AsyncMock()
    maintenance.bind_lifecycle(
        MemoryLifecycleBindRequest(
            get_session=lambda _key: session,
            commit_consolidation=manager.commit_consolidation,
            retry_consumers=manager.retry_memory_consumers,
            record_publication=manager.record_memory_publication,
            record_recent_context=manager.record_recent_context,
            after_consolidation=after_consolidation,
            group_environment=cast(Any, object()),
            runtime_roles=RoleStore(tmp_path),
        )
    )

    result = await maintenance.consolidate(ConsolidateRequest(session=session))

    assert result.trace["mode"] == "markdown"
    after_consolidation.assert_awaited_once_with(session)


async def test_markdown_consolidation_reports_committed_post_consumer_failure(
    tmp_path: Path,
):
    session = SimpleNamespace(
        key="role:mira",
        metadata={"role_id": "mira"},
        messages=[{"role": "user", "content": f"u{i}"} for i in range(12)],
        last_consolidated=0,
    )
    manager = SessionManager(tmp_path)
    session = Session(
        key=session.key,
        metadata=session.metadata,
        messages=[dict(message) for message in session.messages],
    )
    manager.save(session)
    maintenance = MarkdownMemoryMaintenance(
        store=MarkdownMemoryStore(tmp_path),
        provider=cast(Any, SimpleNamespace()),
        model="lm",
        keep_count=6,
    )
    draft = _ConsolidationDraft(
        window=ConsolidationWindow(
            old_messages=list(session.messages[:6]),
            keep_count=6,
            consolidate_up_to=6,
        ),
        segments=ConsolidationSegments(
            user_messages=list(session.messages[:6]), external_messages=[]
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
            commit_consolidation=manager.commit_consolidation,
            retry_consumers=manager.retry_memory_consumers,
            record_publication=manager.record_memory_publication,
            record_recent_context=manager.record_recent_context,
            after_consolidation=_fail,
            group_environment=cast(Any, object()),
            runtime_roles=RoleStore(tmp_path),
        )
    )

    result = await maintenance.consolidate(ConsolidateRequest(session=session))

    assert result.trace["mode"] == "failed"
    assert result.trace["memory_committed"] is True
    assert result.trace["step"] == "consumers"
    assert session.last_consolidated == 6


async def test_default_memory_engine_serializes_lifecycle_maintenance(
    tmp_path: Path,
):
    event_bus = EventBus()
    session = SimpleNamespace(
        key="role:mira",
        metadata={"role_id": "mira"},
        messages=[{"role": "user", "content": "u"}],
        last_consolidated=0,
    )
    maintenance = MarkdownMemoryMaintenance(
        store=MarkdownMemoryStore(tmp_path),
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
            commit_consolidation=AsyncMock(),
            group_environment=cast(Any, object()),
            runtime_roles=RoleStore(tmp_path),
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
