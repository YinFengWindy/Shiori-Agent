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
from bus.events_context import ContextWindowChanged
from shiori_sdk.memory.committed import TurnCommitted
from agent.core.passive_turn.helpers import get_window_history
from conversation.context_scope import (
    history_start,
    turn_context_view,
    user_context_view,
)
from conversation.service import desktop_thread_id
from shiori_sdk.channels.threads import network_thread_id
from shiori_sdk.memory.events import ConsolidationCommitted
from core.memory.member_profiles import MemberKey, MemberProfile, MemberProfiles
from core.roles import RoleStore
from core.memory.group_environment import (
    SUMMARY_LABEL_KEY,
    SUMMARY_UPDATED_AT_KEY,
    GroupEnvironment,
)
from collections.abc import Callable
from core.memory.markdown import (
    ConsolidateRequest,
    MarkdownMemoryMaintenance,
    MarkdownMemoryStore,
    MarkdownMemoryRuntime,
    MemoryLifecycleBindRequest,
)
from core.memory.markdown.contracts import ConsolidationSegments, _ConsolidationDraft
from core.memory.markdown.external_segment import MEMBER_BATCH_SIZE
from core.memory.markdown.formatting import (
    build_consolidation_source_ref,
    _select_consolidation_window,
)
from tests.backend.core.memory.markdown.memory_double import CommittedMemory
from session.manager import Session, SessionManager
from session.manager.models import consolidation_cursor


@pytest.mark.parametrize("fails", [False, True])
async def test_standalone_memory_completion_notifies_after_lock_release(
    memory_harness, fails
):
    h = memory_harness
    session = h.manager.get_or_create("cli:standalone")
    session.metadata["role_id"] = "mira"
    session.add_message("user", "tea")
    session.add_message("assistant", "done")
    h.manager.save(session)
    h.fail = fails
    observed = []
    h.bus.on(
        ContextWindowChanged,
        lambda event: observed.append(
            (event.session_key, h.maintenance.is_busy(session.key))
        ),
    )
    result = await h.maintenance.consolidate(
        ConsolidateRequest(session=session, through_index=2)
    )
    assert result.trace["mode"] == ("failed" if fails else "markdown")
    assert observed == [(session.key, False)]


@pytest.mark.asyncio
async def test_recent_context_has_its_own_source_and_update_version(memory_harness):
    from core.memory.markdown import RefreshRecentTurnsRequest
    from conversation.context_scope import history_start

    h = memory_harness
    session = h.manager.get_or_create("role:mira")
    session.add_message("user", "tea")
    session.add_message("assistant", "yes")
    h.manager.save(session)
    await h.maintenance.refresh_recent_turns(RefreshRecentTurnsRequest(session))
    progress = session.maintenance_progress
    assert progress.recent_context_version == 1
    assert progress.recent_context_source_ids == [
        message["id"] for message in session.messages
    ]
    assert progress.memory_version == progress.relationship_version == 0
    assert history_start(session, user_context_view(h.manager.workspace, "mira")) == 0
    assert (
        await h.maintenance.consolidate(ConsolidateRequest(session, force=True))
    ).trace["mode"] == "markdown"
    assert session.maintenance_progress.memory_version == 1
    assert session.maintenance_progress.relationship_version == 1
    assert session.maintenance_progress.recent_context_version == 2


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
            retry_consumers=manager.retry_memory_consumers,
            record_publication=manager.record_memory_publication,
            record_recent_context=manager.record_recent_context,
            group_environment=GroupEnvironment(tmp_path, manager.conversation_store),
            runtime_roles=RoleStore(tmp_path),
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
        segments=ConsolidationSegments(
            user_messages=list(window.old_messages), external_messages=[]
        ),
        source_ref=build_consolidation_source_ref(window.old_messages),
        history_entry_payloads=[("[2026-09-11 12:00] 你完成了第三轮问题。", 0)],
        pending_items="- [preference] 你喜欢第三轮讨论。",
        conversation="USER: question 2\nASSISTANT: answer 2",
        recent_context_text="# 最近发生的事\n\n第三轮讨论",
        scope_channel="desktop",
        scope_chat_id=session.key,
        archive_all=archive_all,
    )


async def _undo_last_turn(
    manager: SessionManager, memory: CommittedMemory | None, session_key: str
) -> dict[str, Any] | None:
    """Drive the host undo contract the way an undo command consumer does.

    Memory sources are resolved as a dry run inside the session undo, then the
    real rollback runs after the turn is deleted. Returns the rollback result,
    or ``None`` when there was no turn to undo.
    """
    resolved: list[str] = []

    def resolve_sources(message_ids: list[str]) -> list[str]:
        resolved[:] = message_ids
        if memory is None:
            return []
        preview = memory.undo_by_message_sources(message_ids, dry_run=True)
        return list(preview["rollback_source_ids"])

    result = await manager.undo_last_turn(
        session_key, rollback_source_resolver=resolve_sources
    )
    if result is None:
        return None
    if memory is None:
        return {"affected_ids": []}
    return memory.undo_by_message_sources(resolved or result.deleted_ids)


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
        assert await _undo_last_turn(manager, None, session.key) is not None
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
    memory_store = CommittedMemory([message["id"] for message in session.messages])
    memory_engine = memory_store
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
            _undo_last_turn(manager, memory_engine, session.key)
        )
        await asyncio.sleep(0)
        assert not undo_task.done()
        assert len(session.messages) == 6
        resume.set()
        result, rollback = await asyncio.wait_for(
            asyncio.gather(commit_task, undo_task), timeout=2
        )
        assert result.trace["mode"] == "markdown"
        assert rollback is not None and rollback["affected_ids"] == item_ids
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
    manager._store.update_last_consolidated(session.key, 2)
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
    memory_store = CommittedMemory([message["id"] for message in session.messages])
    engine = memory_store
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
        undo_task = asyncio.create_task(_undo_last_turn(manager, engine, session.key))
        for _ in range(5):
            await asyncio.sleep(0)
        assert not undo_task.done()
        assert not task.done()
        assert len(session.messages) == 6
        release.set()
        outcome, rollback = await asyncio.wait_for(
            asyncio.gather(task, undo_task, return_exceptions=True), timeout=2
        )
        assert isinstance(outcome, TimeoutError)
        assert "memory consolidation busy" in str(outcome)
        assert finished.is_set()
        assert isinstance(rollback, dict)
        assert rollback["affected_ids"] == item_ids
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


class _RecordingProvider:
    """记下整理各步收到的提示词，按步骤返回固定结果。"""

    def __init__(self, environment_replies: dict[str, str] | None = None) -> None:
        self.event_prompts: list[str] = []
        self.recent_context_prompts: list[str] = []
        self.environment_prompts: list[str] = []
        self.environment_max_tokens: list[int] = []
        # 群环境整理按会话称呼给出回复；没给的会话回空对象（不更新）。
        self.environment_replies = environment_replies or {}
        # 群环境整理调用期间（准备之后、提交之前）要做的事，模拟小手机的并发编辑。
        self.during_environment: Callable[[], None] | None = None

    async def chat(
        self, *, messages: list[dict[str, str]], max_tokens: int, **_kwargs: Any
    ):
        prompt = messages[-1]["content"]
        if prompt.startswith("群环境整理"):
            self.environment_prompts.append(prompt)
            self.environment_max_tokens.append(max_tokens)
            if self.during_environment is not None:
                self.during_environment()
            reply = next(
                (
                    content
                    for label, content in self.environment_replies.items()
                    if label in prompt
                ),
                "{}",
            )
            return SimpleNamespace(content=reply)
        if "近期语境压缩代理" in prompt:
            self.recent_context_prompts.append(prompt)
            return SimpleNamespace(content='{"active_topics": ["你喜欢猫"]}')
        self.event_prompts.append(prompt)
        return SimpleNamespace(
            content=(
                '{"history_entries": [{"summary": "[2026-09-30 10:00] 你说喜欢猫",'
                ' "emotional_weight": 0}], "pending_items":'
                ' [{"tag": "preference", "content": "你喜欢猫"}]}'
            )
        )


def _recording_maintenance(
    tmp_path: Path,
    manager: SessionManager,
    environment_replies: dict[str, str] | None = None,
    keep_count: int = 0,
):
    """接上真实会话提交、群环境层，记录提示词与引擎事件的整理服务。"""
    provider = _RecordingProvider(environment_replies)
    event_bus = EventBus()
    events: list[ConsolidationCommitted] = []
    event_bus.on(ConsolidationCommitted, lambda event: events.append(event))
    maintenance = MarkdownMemoryMaintenance(
        store=MarkdownMemoryStore(tmp_path),
        provider=cast(LLMProvider, provider),
        model="test",
        keep_count=keep_count,
        event_bus=event_bus,
    )
    maintenance.bind_lifecycle(
        MemoryLifecycleBindRequest(
            get_session=manager.get_or_create,
            commit_consolidation=manager.commit_consolidation,
            retry_consumers=manager.retry_memory_consumers,
            record_publication=manager.record_memory_publication,
            record_recent_context=manager.record_recent_context,
            group_environment=GroupEnvironment(tmp_path, manager.conversation_store),
            runtime_roles=RoleStore(tmp_path),
        )
    )
    return provider, event_bus, events, maintenance


def _add_group_turns(session: Session, group: str, count: int) -> None:
    """群友与角色在群里的 ``count`` 轮对话。"""
    for index in range(count):
        session.add_message(
            "user",
            f"群友第 {index} 句",
            thread_id=group,
            metadata={"message_source": {"sender_id": "555", "group_name": "猫猫群"}},
        )
        session.add_message("assistant", f"回群友第 {index} 句", thread_id=group)


@pytest.mark.asyncio
async def test_external_growth_leaves_the_user_context_window_and_cursor_alone(
    tmp_path: Path,
):
    """群里消息再多、整理再多次，桌面对话的原文窗口不被挤掉（#523）。"""
    manager = SessionManager(tmp_path)
    session = manager.get_or_create("role:mira")
    session.metadata["role_id"] = "mira"
    desktop = desktop_thread_id("mira")
    group = network_thread_id("mira", "qq", "g1")
    session.add_message("user", "我喜欢猫", thread_id=desktop)
    _add_group_turns(session, group, 1)
    session.add_message("assistant", "猫很可爱", thread_id=desktop)
    _add_group_turns(session, group, 12)
    manager.save(session)
    user_view = user_context_view(tmp_path, "mira")
    external_view = turn_context_view(tmp_path, "mira", group)
    user_history = get_window_history(session, user_view)
    provider, event_bus, _events, maintenance = _recording_maintenance(
        tmp_path, manager, keep_count=4
    )
    try:
        external = await maintenance.consolidate(ConsolidateRequest(session=session))
        user_history_after_external = get_window_history(session, user_view)
        # 桌面这边攒够一批（本类最后 4 条之外至少 5 条）才整理，只推进用户游标。
        for index in range(4):
            session.add_message("user", f"桌面第 {index} 句", thread_id=desktop)
            session.add_message("assistant", f"回桌面第 {index} 句", thread_id=desktop)
        await manager.save_async(session)
        external_history = get_window_history(session, external_view)
        user = await maintenance.consolidate(ConsolidateRequest(session=session))
    finally:
        await event_bus.aclose()

    # 外部整理后用户上下文原文不变；用户整理后外部上下文原文不变。
    assert len(user_history) == 2
    assert user_history_after_external == user_history
    assert external.consolidated_count == 22
    assert user.consolidated_count == 6
    assert provider.event_prompts and "群友" not in provider.event_prompts[0]
    manager.invalidate(session.key)
    reloaded = manager.get_or_create(session.key)
    assert len(external_history) == 26
    assert external_history[-1]["content"] == "回群友第 11 句"
    assert get_window_history(reloaded, external_view) == (external_history)
    user_history = get_window_history(reloaded, user_view)
    assert len(user_history) == 10
    assert user_history[-1]["content"] == "回桌面第 3 句"
    assert consolidation_cursor(reloaded, "external") == 24
    assert consolidation_cursor(reloaded, "user") == 32
    assert reloaded.last_consolidated == 24


@pytest.mark.asyncio
async def test_group_members_stay_out_of_the_user_layer_while_the_cursor_covers_them(
    tmp_path: Path,
):
    manager = SessionManager(tmp_path)
    session = manager.get_or_create("role:mira")
    session.metadata["role_id"] = "mira"
    desktop = desktop_thread_id("mira")
    group = network_thread_id("mira", "qq", "g1")
    session.add_message("user", "我喜欢猫", thread_id=desktop)
    session.add_message("assistant", "猫很可爱", thread_id=desktop)
    session.add_message(
        "user",
        "我是阿明，我最喜欢狗",
        thread_id=group,
        metadata={"message_source": {"sender_id": "555", "group_name": "猫猫群"}},
    )
    session.add_message("assistant", "阿明好", thread_id=group)
    session.add_message(
        "user",
        "我明天去面试",
        thread_id=group,
        metadata={
            "message_source": {
                "sender_id": "902",
                "sender_is_user": True,
                "group_name": "猫猫群",
            }
        },
    )
    manager.save(session)
    provider, event_bus, events, maintenance = _recording_maintenance(tmp_path, manager)
    try:
        result = await maintenance.consolidate(
            ConsolidateRequest(session=session, force=True)
        )
        repeated = await maintenance.consolidate(
            ConsolidateRequest(session=session, force=True)
        )
    finally:
        await event_bus.aclose()

    # 用户层整理与引擎只看到用户本人的发言，群里那句带群名。
    [event_prompt] = provider.event_prompts
    [event] = events
    for conversation in (event_prompt, event.conversation):
        assert "我喜欢猫" in conversation
        assert "USER（在群「猫猫群」里）: 我明天去面试" in conversation
        assert "阿明" not in conversation
    # RECENT_CONTEXT 只取用户上下文会话的消息。
    [recent_prompt] = provider.recent_context_prompts
    assert "我喜欢猫" in recent_prompt
    assert "阿明" not in recent_prompt
    assert "我明天去面试" not in recent_prompt
    recent_context = MarkdownMemoryStore(tmp_path / "roles" / "mira")
    assert "阿明" not in recent_context.read_recent_context()
    # 游标一次越过两段；再次整理没有新窗口，不重复写入。
    assert result.consolidated_count == 5
    assert repeated.trace == {"mode": "skipped"}
    manager.invalidate(session.key)
    assert manager.get_or_create(session.key).last_consolidated == 5


@pytest.mark.asyncio
async def test_window_of_only_group_members_skips_extraction_but_moves_the_cursor(
    tmp_path: Path,
):
    manager = SessionManager(tmp_path)
    session = manager.get_or_create("role:mira")
    session.metadata["role_id"] = "mira"
    group = network_thread_id("mira", "qq", "g1")
    session.add_message(
        "user",
        "我是阿明，我最喜欢狗",
        thread_id=group,
        metadata={"message_source": {"sender_id": "555", "group_name": "猫猫群"}},
    )
    session.add_message("assistant", "阿明好", thread_id=group)
    manager.save(session)
    provider, event_bus, events, maintenance = _recording_maintenance(tmp_path, manager)
    try:
        result = await maintenance.consolidate(
            ConsolidateRequest(session=session, force=True)
        )
    finally:
        await event_bus.aclose()

    assert provider.event_prompts == []
    assert events == []
    assert result.consolidated_count == 2
    manager.invalidate(session.key)
    assert manager.get_or_create(session.key).last_consolidated == 2


def test_group_member_turn_still_triggers_consolidation():
    maintenance = MarkdownMemoryMaintenance.__new__(MarkdownMemoryMaintenance)
    enqueued: list[str] = []
    maintenance._enqueue_maintenance = enqueued.append

    maintenance.on_turn_committed(
        TurnCommitted(
            session_key="role:mira",
            channel="qq",
            chat_id="g1",
            input_message="我最喜欢狗",
            persisted_user_message="我最喜欢狗",
            assistant_response="好",
            tools_used=[],
            extra={"skip_post_memory": True, "not_user_authored": True},
        )
    )

    assert enqueued == ["role:mira"]


@pytest.mark.asyncio
async def test_external_segment_updates_each_threads_recent_activity_and_note(
    tmp_path: Path,
):
    manager = SessionManager(tmp_path)
    session = manager.get_or_create("role:mira")
    session.metadata["role_id"] = "mira"
    group = network_thread_id("mira", "qq", "g1")
    stranger = network_thread_id("mira", "qq", "p9")
    session.add_message(
        "user",
        "我是阿明，我最喜欢狗",
        thread_id=group,
        metadata={
            "message_source": {
                "chat_type": "group",
                "group_name": "猫猫群",
                "sender_id": "555",
                "sender_name": "阿明",
            }
        },
    )
    session.add_message("assistant", "阿明好", thread_id=group)
    session.add_message(
        "user",
        "你好呀",
        thread_id=stranger,
        metadata={
            "message_source": {
                "chat_type": "private",
                "sender_id": "777",
                "sender_name": "路人甲",
            }
        },
    )
    manager.save(session)
    replies = {
        "群「猫猫群」": (
            '{"recent_activity": "阿明说他最喜欢狗。", "group_note": "## 氛围\\n轻松"}'
        ),
        "与「路人甲」的私聊": (
            '{"recent_activity": "路人甲来打了招呼。", "group_note": "## 氛围\\n陌生"}'
        ),
    }
    provider, event_bus, _events, maintenance = _recording_maintenance(
        tmp_path, manager, replies
    )
    try:
        result = await maintenance.consolidate(
            ConsolidateRequest(session=session, force=True)
        )
    finally:
        await event_bus.aclose()

    # 每个外部会话单独整理一次；群聊与陌生私聊各自产出最近动态与群笔记。
    assert len(provider.environment_prompts) == 2
    environment = GroupEnvironment(tmp_path, manager.conversation_store)
    for thread, label, summary, note in (
        (group, "群「猫猫群」", "阿明说他最喜欢狗。", "## 氛围\n轻松"),
        (stranger, "与「路人甲」的私聊", "路人甲来打了招呼。", "## 氛围\n陌生"),
    ):
        state = manager.conversation_store.get_thread_state(thread)
        assert state is not None
        assert state.summary == summary
        assert state.metadata[SUMMARY_LABEL_KEY] == label
        assert SUMMARY_UPDATED_AT_KEY in state.metadata
        assert environment.read_note("mira", thread) == note
    assert result.consolidated_count == 3


@pytest.mark.asyncio
async def test_failed_external_thread_keeps_the_whole_window_uncommitted(
    tmp_path: Path,
):
    manager = SessionManager(tmp_path)
    session = manager.get_or_create("role:mira")
    session.metadata["role_id"] = "mira"
    group = network_thread_id("mira", "qq", "g1")
    session.add_message(
        "user",
        "我是阿明",
        thread_id=group,
        metadata={"message_source": {"sender_id": "555", "group_name": "猫猫群"}},
    )
    manager.save(session)
    provider, event_bus, _events, maintenance = _recording_maintenance(
        tmp_path, manager, {"群「猫猫群」": "not json"}
    )
    try:
        result = await maintenance.consolidate(
            ConsolidateRequest(session=session, force=True)
        )
    finally:
        await event_bus.aclose()

    assert result.trace["mode"] == "failed"
    assert result.trace["error"] == "invalid_json"
    manager.invalidate(session.key)
    assert manager.get_or_create(session.key).last_consolidated == 0


@pytest.mark.asyncio
async def test_group_turn_budget_force_only_advances_the_external_cursor(
    tmp_path: Path,
):
    """群回合预算不够、走到强制整理时，也只推进外部游标，桌面原文不动（#523）。"""
    manager = SessionManager(tmp_path)
    session = manager.get_or_create("role:mira")
    session.metadata["role_id"] = "mira"
    desktop = desktop_thread_id("mira")
    group = network_thread_id("mira", "qq", "g1")
    session.add_message("user", "我喜欢猫", thread_id=desktop)
    session.add_message("assistant", "猫很可爱", thread_id=desktop)
    _add_group_turns(session, group, 3)
    manager.save(session)
    user_view = user_context_view(tmp_path, "mira")
    user_history = get_window_history(session, user_view)
    _provider, event_bus, _events, maintenance = _recording_maintenance(
        tmp_path, manager, keep_count=4
    )
    try:
        prepared = await manager.prepare_window(
            session.key, turn_context_view(tmp_path, "mira", group), keep_turns=0
        )
        assert prepared is not None
        result = await maintenance.ensure_memory_for_window(prepared)
        assert result.trace["mode"] == "markdown"
        # The prerequisite owner advances memory only; publication belongs to compaction.
        assert history_start(session, prepared.view) == 0
    finally:
        await event_bus.aclose()

    manager.invalidate(session.key)
    reloaded = manager.get_or_create(session.key)
    assert get_window_history(reloaded, user_view) == user_history
    assert consolidation_cursor(reloaded, "user") == 0
    assert consolidation_cursor(reloaded, "external") == len(reloaded.messages)


@pytest.mark.asyncio
async def test_role_session_without_role_metadata_consolidates_after_undo(
    tmp_path: Path,
):
    """会话键是 role:<id> 就按上下文游标，撤销与整理对同一会话判定一致。"""
    manager = SessionManager(tmp_path)
    session = manager.get_or_create("role:mira")
    desktop = desktop_thread_id("mira")
    for index in range(3):
        session.add_message("user", f"桌面第 {index} 句", thread_id=desktop)
        session.add_message("assistant", f"回桌面第 {index} 句", thread_id=desktop)
    manager.save(session)
    assert await manager.undo_last_turn(session.key) is not None
    assert session.context_cursors == {"user": 0, "external": 0}
    _provider, event_bus, _events, maintenance = _recording_maintenance(
        tmp_path, manager
    )
    try:
        result = await maintenance.consolidate(
            ConsolidateRequest(session=session, force=True)
        )
    finally:
        await event_bus.aclose()

    assert result.trace["mode"] == "markdown"
    assert session.context_cursors == {"user": 4, "external": 4}


def _member_message(
    session: Session, content: str, thread_id: str, **source: object
) -> None:
    session.add_message(
        "user",
        content,
        thread_id=thread_id,
        metadata={"message_source": {"chat_type": "group", **source}},
    )


@pytest.mark.asyncio
async def test_external_segment_updates_member_profiles_but_never_the_users(
    tmp_path: Path,
):
    manager = SessionManager(tmp_path)
    session = manager.get_or_create("role:mira")
    session.metadata["role_id"] = "mira"
    cats = network_thread_id("mira", "qq", "g1")
    dogs = network_thread_id("mira", "qq", "g2")
    telegram = network_thread_id("mira", "telegram", "g3")
    _member_message(
        session,
        "我最喜欢狗",
        cats,
        channel="qq",
        sender_id="555",
        sender_name="阿明",
        group_name="猫猫群",
    )
    _member_message(
        session,
        "我明天去面试",
        cats,
        channel="qq",
        sender_id="902",
        sender_name="小风",
        group_name="猫猫群",
        sender_is_user=True,
    )
    _member_message(
        session,
        "改名了",
        dogs,
        channel="qq",
        sender_id="555",
        sender_name="明哥",
        group_name="狗狗群",
    )
    _member_message(
        session,
        "hi",
        telegram,
        channel="telegram",
        sender_id="555",
        sender_name="Ming",
        group_name="电报群",
    )
    manager.save(session)
    replies = {
        "群「猫猫群」": (
            '{"members": {"555": {"profile": "## 印象\n爱狗", "brief": "阿明：爱狗"},'
            ' "902": {"profile": "不该写", "brief": "不该写"}}}'
        ),
        "群「狗狗群」": (
            '{"members": {"555": {"profile": "## 印象\n爱狗，改名明哥",'
            ' "brief": "明哥：爱狗"}}}'
        ),
    }
    provider, event_bus, _events, maintenance = _recording_maintenance(
        tmp_path, manager, replies
    )
    try:
        result = await maintenance.consolidate(
            ConsolidateRequest(session=session, force=True)
        )
    finally:
        await event_bus.aclose()

    assert result.trace["mode"] == "markdown"
    members = MemberProfiles(tmp_path)
    # 同一渠道两个群的发言合并为一份，后一个群在前一个群的结果上更新。
    [_, dogs_prompt, _] = provider.environment_prompts
    assert "阿明：爱狗" in dogs_prompt
    qq = members.read("mira", MemberKey("qq", "555"))
    assert qq is not None
    assert qq.nicknames == ("阿明", "明哥")
    assert qq.thread_ids == (cats, dogs)
    assert qq.profile == "## 印象\n爱狗，改名明哥"
    assert qq.brief == "明哥：爱狗"
    # 另一渠道的相同 ID 是另一份档案；用户本人不产生档案。
    telegram_member = members.read("mira", MemberKey("telegram", "555"))
    assert telegram_member is not None and telegram_member.nicknames == ("Ming",)
    assert members.read("mira", MemberKey("qq", "902")) is None
    assert len(members.list("mira")) == 2


@pytest.mark.asyncio
async def test_many_members_are_consolidated_in_bounded_batches(tmp_path: Path):
    manager = SessionManager(tmp_path)
    session = manager.get_or_create("role:mira")
    session.metadata["role_id"] = "mira"
    group = network_thread_id("mira", "qq", "g1")
    for index in range(MEMBER_BATCH_SIZE + 2):
        _member_message(
            session,
            "hi",
            group,
            channel="qq",
            sender_id=str(index),
            sender_name=f"人{index}",
            group_name="猫猫群",
        )
    manager.save(session)
    provider, event_bus, _events, maintenance = _recording_maintenance(
        tmp_path, manager
    )
    try:
        result = await maintenance.consolidate(
            ConsolidateRequest(session=session, force=True)
        )
    finally:
        await event_bus.aclose()

    assert result.trace["mode"] == "markdown"
    # 第一批带群环境，第二批只整理剩下的成员；每次输出上限不随成员数无限增长。
    first, second = provider.environment_prompts
    assert "现有群笔记" in first and "现有群笔记" not in second
    assert "### 人9（9）" in second and "### 人9（9）" not in first
    assert max(provider.environment_max_tokens) <= 2048 + 400 * MEMBER_BATCH_SIZE
    assert len(MemberProfiles(tmp_path).list("mira")) == MEMBER_BATCH_SIZE + 2


@pytest.mark.asyncio
@pytest.mark.parametrize("edited", ["group_note", "member_profile"])
async def test_phone_edits_made_while_preparing_are_not_overwritten(
    tmp_path: Path, edited: str
):
    manager = SessionManager(tmp_path)
    session = manager.get_or_create("role:mira")
    session.metadata["role_id"] = "mira"
    group = network_thread_id("mira", "qq", "g1")
    _member_message(
        session,
        "我最喜欢狗",
        group,
        channel="qq",
        sender_id="555",
        sender_name="阿明",
        group_name="猫猫群",
    )
    manager.save(session)
    environment = GroupEnvironment(tmp_path, manager.conversation_store)
    members = MemberProfiles(tmp_path)
    key = MemberKey("qq", "555")
    environment.write_note("mira", group, "旧笔记")
    members.write("mira", MemberProfile(key=key, nicknames=("阿明",), brief="旧速记"))
    replies = {
        "群「猫猫群」": (
            '{"group_note": "模型笔记",'
            ' "members": {"555": {"profile": "模型档案", "brief": "模型速记"}}}'
        ),
    }
    provider, event_bus, _events, maintenance = _recording_maintenance(
        tmp_path, manager, replies
    )

    def phone_edit() -> None:
        if edited == "group_note":
            environment.write_note("mira", group, "用户笔记")
        else:
            members.write(
                "mira", MemberProfile(key=key, nicknames=("阿明",), brief="用户速记")
            )

    provider.during_environment = phone_edit
    try:
        stale = await maintenance.consolidate(
            ConsolidateRequest(session=session, force=True)
        )
        # 什么都没写，游标不动：用户的编辑原样保留。
        assert stale.trace == {"mode": "skipped", "reason": "stale"}
        assert session.last_consolidated == 0
        expected_note = "用户笔记" if edited == "group_note" else "旧笔记"
        assert environment.read_note("mira", group) == expected_note
        profile = members.read("mira", key)
        assert profile is not None
        assert profile.brief == ("用户速记" if edited == "member_profile" else "旧速记")

        # 下次以新内容为快照重来，照常提交。
        provider.during_environment = None
        retried = await maintenance.consolidate(
            ConsolidateRequest(session=session, force=True)
        )
    finally:
        await event_bus.aclose()

    assert retried.trace["mode"] == "markdown"
    assert environment.read_note("mira", group) == "模型笔记"
    profile = members.read("mira", key)
    assert profile is not None and profile.brief == "模型速记"
