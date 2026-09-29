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
from bus.events_lifecycle import TurnCommitted
from conversation.service import desktop_thread_id, network_thread_id
from core.memory.events import ConsolidationCommitted
from core.memory.member_profiles import MemberKey, MemberProfiles
from core.memory.group_environment import (
    SUMMARY_LABEL_KEY,
    SUMMARY_UPDATED_AT_KEY,
    GroupEnvironment,
)
from core.memory.markdown import (
    ConsolidateRequest,
    MarkdownMemoryMaintenance,
    MarkdownMemoryStore,
    MarkdownMemoryRuntime,
    MemoryLifecycleBindRequest,
)
from core.memory.markdown.contracts import ConsolidationSegments, _ConsolidationDraft
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
            group_environment=GroupEnvironment(tmp_path, manager.conversation_store),
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
        source_ref=_build_consolidation_source_ref(window.old_messages),
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


class _RecordingProvider:
    """记下整理各步收到的提示词，按步骤返回固定结果。"""

    def __init__(self, environment_replies: dict[str, str] | None = None) -> None:
        self.event_prompts: list[str] = []
        self.recent_context_prompts: list[str] = []
        self.environment_prompts: list[str] = []
        # 群环境整理按会话称呼给出回复；没给的会话回空对象（不更新）。
        self.environment_replies = environment_replies or {}

    async def chat(self, *, messages: list[dict[str, str]], **_kwargs: Any):
        prompt = messages[-1]["content"]
        if prompt.startswith("群环境整理"):
            self.environment_prompts.append(prompt)
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
        keep_count=0,
        event_bus=event_bus,
    )
    maintenance.bind_lifecycle(
        MemoryLifecycleBindRequest(
            get_session=manager.get_or_create,
            commit_consolidation=manager.commit_consolidation,
            group_environment=GroupEnvironment(tmp_path, manager.conversation_store),
        )
    )
    return provider, event_bus, events, maintenance


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
