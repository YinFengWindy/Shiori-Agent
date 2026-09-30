"""Passive turns own same-role desktop pushes until their ordered SQL commit."""

import asyncio
from conversation.listening import GroupListeningControl
from conversation.service import ConversationService
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from agent.core.passive_turn.pipeline import AgentCoreDeps, PassiveTurnPipeline
from agent.core.passive_turn.reasoner import DefaultReasoner
from agent.core.runtime_support import ToolDiscoveryState, TurnRunResult
from agent.core.types import ContextBundle, ReasonerResult
from agent.lifecycle.types import PromptRenderResult
from agent.looping.ports import LLMConfig, LLMServices
from agent.tool_hooks import ToolExecutionRequest
from agent.tool_hooks.executor import ToolExecutor
from agent.tools.message_push import MessagePushTool
from agent.tools.registry import ToolRegistry
from bus.event_bus import EventBus
from bus.events import InboundMessage
from agent.turns.turn_pushes import current_turn_pushes
from conversation.push_sync import ExternalPushSyncService
from conversation.service import (
    desktop_thread_id,
    network_thread_id,
    scheduler_thread_id,
)
from core.accounts import AccountRecord
from core.identity import IdentityChat, UserIdentityStore
from core.roles import RoleStore
from core.roles.reply_state import RoleReply
from desktop_bridge.service import DesktopBridgeService
from session.manager import SessionManager
from core.memory.group_environment import GroupEnvironment


@pytest.fixture
async def runtime(tmp_path):
    roles = RoleStore(tmp_path)
    roles.create_role(role_id="mira", name="Mira", system_prompt="test")
    manager = SessionManager(tmp_path)
    bus = EventBus()
    push = MessagePushTool(event_bus=bus)
    bridge = DesktopBridgeService(
        workspace=tmp_path,
        role_store=roles,
        session_manager=manager,
        group_listening=GroupListeningControl(
            ConversationService(manager), lambda _channel: False
        ),
        group_environment=GroupEnvironment(tmp_path, manager.conversation_store),
        agent_loop=SimpleNamespace(),
        event_bus=bus,
        push_tool=push,
    )
    session = (await bridge.app_service.open_role_session("mira")).session
    tools = ToolRegistry()
    tools.register(push)
    emitted = []
    bridge.add_event_listener(emitted.append)

    async def call(**payload):
        result = await ToolExecutor().execute(
            ToolExecutionRequest(
                call_id="push",
                tool_name="message_push",
                source="passive",
                arguments={"channel": "desktop", "chat_id": "role:mira", **payload},
                session_key=session.key,
            ),
            tools.execute,
        )
        return str(result.output)

    def pipeline(reasoning):
        return PassiveTurnPipeline(
            AgentCoreDeps(
                session=SimpleNamespace(session_manager=manager, presence=None),
                context_store=SimpleNamespace(
                    prepare=AsyncMock(return_value=ContextBundle())
                ),
                context=SimpleNamespace(
                    render=Mock(
                        return_value=SimpleNamespace(system_prompt="", messages=[])
                    )
                ),
                tools=tools,
                reasoner=SimpleNamespace(run_turn=reasoning),
                event_bus=bus,
            )
        )

    yield SimpleNamespace(
        manager=manager,
        bridge=bridge,
        session=session,
        emitted=emitted,
        call=call,
        pipeline=pipeline,
        push=push,
        bus=bus,
    )
    await bridge.aclose()


def incoming():
    return InboundMessage(
        channel="qqbot",
        chat_id="friend",
        sender="user",
        content="send to desktop",
        timestamp=datetime(2026, 9, 26, 0, 21, 44, tzinfo=timezone.utc),
        metadata={
            "role_id": "mira",
            "thread_id": network_thread_id("mira", "qqbot", "friend"),
        },
    )


def reply(formal=True):
    return TurnRunResult(
        reply="done",
        tools_used=["message_push"],
        context_retry={"formal_role_reply": formal},
        role_reply=RoleReply(content="done", mood="平静", thought="完成了"),
    )


@pytest.mark.parametrize("formal", [True, False])
async def test_pipeline_commits_ordered_pushes_and_emits_complete_turn(
    runtime, tmp_path, formal
):
    observed = {}

    async def reasoning(**_kwargs):
        # The actual executor/registry path must keep the passive turn identity.
        observed["first"] = await runtime.call(message="first", image="first.png")
        observed["second"] = await runtime.call(message="second")
        observed["messages"] = list(runtime.session.messages)
        observed["persisted"] = runtime.manager._store.fetch_session_messages(
            runtime.session.key
        )
        observed["events"] = list(runtime.emitted)
        return reply(formal)

    msg = incoming()
    result = await runtime.pipeline(reasoning).run(
        msg, runtime.session.key, dispatch_outbound=False
    )
    expected = ["send to desktop", "first", "", "second", "done"]
    reloaded = SessionManager(tmp_path).get_or_create(runtime.session.key)
    assert [row["content"] for row in reloaded.messages] == expected
    assert observed == {
        "first": "文本已排队，回合成功后发送；图片已排队，回合成功后发送",
        "second": "文本已排队，回合成功后发送",
        "messages": [],
        "persisted": [],
        "events": [],
    }
    assert len({row["id"] for row in reloaded.messages}) == 5
    assert datetime.fromisoformat(reloaded.messages[0]["timestamp"]) == msg.timestamp
    assert reloaded.messages[2]["media"] == ["first.png"]
    assert result.committed_message_id == reloaded.messages[-1]["id"]
    assert len(runtime.emitted) == 1
    # The desktop timeline receives the desktop pushes, not the QQ turn itself.
    assert [row["content"] for row in runtime.emitted[0]["payload"]["messages"]] == [
        "first",
        "",
        "second",
    ]
    # Older pages retain the same authoritative sequence after reopening.
    newest = runtime.manager._store.fetch_messages_page(runtime.session.key, limit=2)
    older = runtime.manager._store.fetch_messages_page(
        runtime.session.key, limit=3, before_seq=newest["next_before_seq"]
    )
    assert [
        row["content"] for row in older["messages"] + newest["messages"]
    ] == expected


@pytest.mark.parametrize("failure_stage", ["reasoning", "append"])
@pytest.mark.parametrize("cancelled", [False, True])
async def test_pipeline_discards_push_drafts_on_failure_or_cancellation(
    runtime, monkeypatch, failure_stage, cancelled
):
    failure = asyncio.CancelledError() if cancelled else OSError("failed")

    async def reasoning(**_kwargs):
        assert "已排队" in await runtime.call(message="must not survive")
        if failure_stage == "reasoning":
            raise failure
        return reply()

    if failure_stage == "append":
        monkeypatch.setattr(
            runtime.manager, "append_messages", AsyncMock(side_effect=failure)
        )
    operation = runtime.pipeline(reasoning).run(
        incoming(), runtime.session.key, dispatch_outbound=False
    )
    if cancelled or failure_stage == "append":
        with pytest.raises(type(failure)):
            await operation
    else:
        assert (await operation).content == "处理消息时出错，请稍后再试。"
    assert runtime.session.messages == []
    assert runtime.manager._store.fetch_session_messages(runtime.session.key) == []
    assert runtime.emitted == []
    # A later independent push must not be captured by the abandoned turn.
    assert "已发送" in await runtime.call(message="later")
    assert [row["content"] for row in runtime.session.messages] == ["later"]


async def test_pipeline_keeps_background_other_role_and_external_sends_independent(
    runtime,
):
    external = AsyncMock(return_value=None)
    runtime.push.register_channel("external", text=external)

    async def reasoning(**_kwargs):
        assert "已发送" in await asyncio.create_task(runtime.call(message="background"))
        assert "已发送" in await runtime.call(chat_id="role:other", message="other")
        assert "已发送" in await runtime.call(
            channel="external", chat_id="friend", message="external"
        )
        assert "已排队" in await runtime.call(message="queued")
        assert [row["content"] for row in runtime.session.messages] == ["background"]
        raise RuntimeError("turn failed")

    await runtime.pipeline(reasoning).run(
        incoming(), runtime.session.key, dispatch_outbound=False
    )
    assert [row["content"] for row in runtime.session.messages] == ["background"]
    assert [
        row["content"] for row in runtime.manager.get_or_create("role:other").messages
    ] == ["other"]
    external.assert_awaited_once_with("friend", "external")


async def test_cancel_while_waiting_to_commit_cannot_leak_pushes_into_queued_save(
    runtime, monkeypatch
):
    append_entered = asyncio.Event()
    original_append = runtime.manager.append_messages

    async def append(*args, **kwargs):
        append_entered.set()
        return await original_append(*args, **kwargs)

    async def reasoning(**_kwargs):
        await runtime.call(message="private")
        return reply()

    monkeypatch.setattr(runtime.manager, "append_messages", append)
    async with runtime.manager._lock(runtime.session.key):
        task = asyncio.create_task(
            runtime.pipeline(reasoning).run(
                incoming(), runtime.session.key, dispatch_outbound=False
            )
        )
        await append_entered.wait()
        runtime.manager.save(runtime.session)
        assert runtime.manager._store.fetch_session_messages(runtime.session.key) == []
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert runtime.session.messages == []
    assert runtime.emitted == []


# ── Context isolation: what history the model is sent for each kind of turn ──

QQ_ACCOUNT = AccountRecord(
    id="qq:101",
    plugin_id="qq",
    platform="qq",
    platform_account_id="101",
    config_ref="101",
    role_id="mira",
)
DESKTOP = desktop_thread_id("mira")
USER_DM = network_thread_id("mira", "qq", "902")
STRANGER_DM = network_thread_id("mira", "qq", "555")
GROUP_A = network_thread_id("mira", "qq", "group:7")
GROUP_B = network_thread_id("mira", "qq", "group:8")
_LABELS = ("desk", "udm", "sdm", "ga", "gb")


def _bind(workspace, chat_id):
    store = UserIdentityStore(workspace)
    assert store.pair(
        store.create_pairing_code().code,
        record=QQ_ACCOUNT,
        user_id=chat_id,
        scope="platform",
        chat=IdentityChat(QQ_ACCOUNT.id, "qq", chat_id),
    )


def _seed_role_session(manager, *, group_text="said in group a"):
    """One exchange per thread; the bound user (902) also speaks in group A."""
    session = manager.get_or_create("role:mira")
    session.metadata["role_id"] = "mira"
    for label, thread, text in (
        ("desk", DESKTOP, "said on desktop"),
        ("udm", USER_DM, "said in user dm"),
        ("sdm", STRANGER_DM, "said in stranger dm"),
        ("ga", GROUP_A, group_text),
        ("gb", GROUP_B, "said in group b"),
    ):
        metadata = {"sender_is_user": True} if thread == GROUP_A else {}
        session.add_message(
            "user", f"{label}-user {text}", thread_id=thread, metadata=metadata
        )
        session.add_message("assistant", f"{label}-reply", thread_id=thread)
    manager.save(session)
    return session


def _isolation_pipeline(manager, *, input_token_threshold=75000):
    reasoner = DefaultReasoner(
        llm=LLMServices(provider=AsyncMock(), light_provider=AsyncMock()),
        llm_config=LLMConfig(),
        tools=ToolRegistry(),
        discovery=ToolDiscoveryState(),
        tool_search_enabled=False,
        memory_window=40,
        context=AsyncMock(),
        session_manager=manager,
    )
    reasoner.render_prompt = AsyncMock(
        side_effect=lambda request: PromptRenderResult(
            messages=[*request.history, {"role": "user", "content": request.content}]
        )
    )
    role_reply = RoleReply(content="ok", mood="平静", thought="好")
    reasoner.run = AsyncMock(
        return_value=ReasonerResult(reply="ok", metadata={"role_reply": role_reply})
    )
    pipeline = PassiveTurnPipeline(
        AgentCoreDeps(
            session=SimpleNamespace(session_manager=manager, presence=None),
            context_store=SimpleNamespace(
                prepare=AsyncMock(return_value=ContextBundle())
            ),
            context=SimpleNamespace(
                render=Mock(return_value=SimpleNamespace(system_prompt="", messages=[]))
            ),
            tools=ToolRegistry(),
            reasoner=reasoner,
            event_bus=EventBus(),
            memory_input_token_threshold=input_token_threshold,
        )
    )
    return pipeline, reasoner


def _turn(thread, channel="qq", chat_id="x"):
    return InboundMessage(
        channel=channel,
        chat_id=chat_id,
        sender="someone",
        content="now",
        timestamp=datetime(2026, 9, 29, tzinfo=timezone.utc),
        metadata={"role_id": "mira", "thread_id": thread},
    )


async def _model_history(tmp_path, thread):
    """Runs one turn in ``thread`` and returns the history texts the model got."""
    manager = SessionManager(tmp_path)
    pipeline, reasoner = _isolation_pipeline(manager)
    await pipeline.run(_turn(thread), "role:mira", dispatch_outbound=False)
    sent = reasoner.run.await_args.args[0][:-1]
    return [str(message["content"]) for message in sent]


def _labels(history):
    return [
        label
        for label in _LABELS
        if any(f"{label}-user" in text or f"{label}-reply" in text for text in history)
    ]


@pytest.mark.parametrize("thread", [DESKTOP, USER_DM])
async def test_user_context_turn_sees_desktop_and_user_dm_only(tmp_path, thread):
    _bind(tmp_path, "902")
    _seed_role_session(SessionManager(tmp_path))

    history = await _model_history(tmp_path, thread)

    assert _labels(history) == ["desk", "udm"]


async def test_scheduled_job_without_source_thread_runs_in_user_context(tmp_path):
    _bind(tmp_path, "902")
    _seed_role_session(SessionManager(tmp_path))
    # The thread a scheduled job created without a source thread runs in.
    thread = scheduler_thread_id("mira", "job-1")

    history = await _model_history(tmp_path, thread)

    assert _labels(history) == ["desk", "udm"]


@pytest.mark.parametrize(
    ("thread", "label"), [(GROUP_A, "ga"), (GROUP_B, "gb"), (STRANGER_DM, "sdm")]
)
async def test_external_turn_sees_only_its_own_conversation(tmp_path, thread, label):
    """Other groups and stranger private chats stay out of an external turn (#539)."""
    _bind(tmp_path, "902")
    _seed_role_session(SessionManager(tmp_path))

    history = await _model_history(tmp_path, thread)

    assert _labels(history) == [label]


async def test_group_turn_history_is_dialog_only_but_members_include_heard(tmp_path):
    """Listening records stay out of the history (they form their own block at
    the tail, #539), yet the group's heard members still reach member profiles."""
    _bind(tmp_path, "902")
    manager = SessionManager(tmp_path)
    _seed_role_session(manager)
    listening = manager.conversation_store.listening
    before = datetime.now().astimezone() - timedelta(hours=1)
    for thread, sender_id in ((GROUP_A, "71"), (GROUP_B, "72")):
        listening.switches.set_enabled(thread, True, operator="user")
        listening.hear(
            thread,
            sender_id=sender_id,
            content="heard",
            source={"channel": "qq", "sender_id": sender_id},
            external_message_id="",
            timestamp=before,
        )
    pipeline, reasoner = _isolation_pipeline(manager)

    await pipeline.run(_turn(GROUP_B), "role:mira", dispatch_outbound=False)

    history = [str(m["content"]) for m in reasoner.run.await_args.args[0][:-1]]
    assert _labels(history) == ["gb"]
    assert not any("heard" in text for text in history)
    request = reasoner.render_prompt.await_args.args[0]
    # Group B's heard member comes first (heard an hour before the dialog, whose
    # seeded message has no sender); group A's heard member stays out.
    assert [source.sender_id for source in request.window_sources] == ["72", None]


async def test_bound_stranger_dm_joins_user_context_once_after_the_cursor(
    tmp_path,
):
    _bind(tmp_path, "902")
    manager = SessionManager(tmp_path)
    session = manager.get_or_create("role:mira")
    session.metadata["role_id"] = "mira"
    session.add_message("user", "sdm-old consolidated", thread_id=STRANGER_DM)
    session.add_message("assistant", "sdm-old-reply", thread_id=STRANGER_DM)
    session.last_consolidated = 2
    manager.save(session)
    _seed_role_session(manager)
    assert _labels(await _model_history(tmp_path, DESKTOP)) == ["desk", "udm"]

    _bind(tmp_path, "555")
    history = await _model_history(tmp_path, DESKTOP)

    assert _labels(history) == ["desk", "udm", "sdm"]
    assert sum("sdm-user" in text for text in history) == 1
    assert not any("sdm-old" in text for text in history)


async def test_input_budget_counts_only_the_turn_context(tmp_path):
    _bind(tmp_path, "902")
    manager = SessionManager(tmp_path)
    _seed_role_session(manager, group_text="x" * 40000)

    for thread, runs in ((DESKTOP, True), (GROUP_B, True), (GROUP_A, False)):
        pipeline, reasoner = _isolation_pipeline(manager, input_token_threshold=2000)
        await pipeline.run(_turn(thread), "role:mira", dispatch_outbound=False)
        # The large group A message only weighs on group A's own turns, where
        # the context guard stops the turn before the model is called.
        assert reasoner.run.await_count == (1 if runs else 0)


async def test_channel_pushes_during_a_turn_are_committed_with_it_under_their_chat(
    runtime,
):
    _ = ExternalPushSyncService(
        live_turn_pushes=current_turn_pushes,
        session_manager=runtime.manager,
        event_bus=runtime.bus,
    )
    runtime.push.register_channel("qq", text=AsyncMock(return_value="qq-msg-1"))
    runtime.push.register_channel(
        "qqfail", text=AsyncMock(side_effect=OSError("offline"))
    )
    target = network_thread_id("mira", "qq", "gqq:6")

    async def reasoning(**_kwargs):
        assert "已发送" in await runtime.call(
            channel="qq", chat_id="gqq:6", message="去另一个群说一声"
        )
        assert "发送失败" in await runtime.call(
            channel="qqfail", chat_id="gqq:7", message="没发出去"
        )
        # Not recorded before the turn commits.
        assert runtime.manager._store.fetch_session_messages(runtime.session.key) == []
        return reply()

    await runtime.pipeline(reasoning).run(
        incoming(), runtime.session.key, dispatch_outbound=False
    )

    stored = runtime.manager._store.fetch_session_messages(runtime.session.key)
    assert [(row["content"], row["thread_id"]) for row in stored] == [
        ("send to desktop", network_thread_id("mira", "qqbot", "friend")),
        ("去另一个群说一声", target),
        ("done", network_thread_id("mira", "qqbot", "friend")),
    ]
    assert stored[1]["metadata"]["external_message_id"] == "qq-msg-1"
    # The turn's commit carries it, so the phone hears about the target chat.
    phone = [
        event["payload"]
        for event in runtime.emitted
        if event["method"] == "phone.conversation.updated"
    ]
    assert [
        (update["thread_id"], [row["id"] for row in update["messages"]])
        for update in phone
    ] == [(target, [stored[1]["id"]])]


async def test_a_committed_turns_delivered_image_is_recorded_once_under_its_chat(
    runtime,
):
    _ = ExternalPushSyncService(
        live_turn_pushes=current_turn_pushes,
        session_manager=runtime.manager,
        event_bus=runtime.bus,
    )
    runtime.push.register_channel("qq", image=AsyncMock(return_value=None))

    async def reasoning(**_kwargs):
        assert "已发送" in await runtime.call(
            channel="qq", chat_id="gqq:6", image="scene.png"
        )
        return reply()

    await runtime.pipeline(reasoning).run(
        incoming(), runtime.session.key, dispatch_outbound=False
    )

    stored = runtime.manager._store.fetch_session_messages(runtime.session.key)
    assert [
        (row["content"], row.get("media"), row["thread_id"])
        for row in stored
        if row["role"] == "assistant"
    ] == [
        ("", ["scene.png"], network_thread_id("mira", "qq", "gqq:6")),
        ("done", None, network_thread_id("mira", "qqbot", "friend")),
    ]


async def test_a_failed_turn_still_records_the_channel_push_it_delivered(runtime):
    _ = ExternalPushSyncService(
        live_turn_pushes=current_turn_pushes,
        session_manager=runtime.manager,
        event_bus=runtime.bus,
    )
    runtime.push.register_channel("qq", text=AsyncMock(return_value="qq-msg-1"))

    async def reasoning(**_kwargs):
        assert "已发送" in await runtime.call(
            channel="qq", chat_id="gqq:6", message="去另一个群说一声"
        )
        assert "已排队" in await runtime.call(message="never delivered")
        raise RuntimeError("turn failed")

    await runtime.pipeline(reasoning).run(
        incoming(), runtime.session.key, dispatch_outbound=False
    )

    # The desktop draft was never sent and is dropped; the delivered push is kept.
    stored = runtime.manager._store.fetch_session_messages(runtime.session.key)
    assert [(row["content"], row["thread_id"]) for row in stored] == [
        ("去另一个群说一声", network_thread_id("mira", "qq", "gqq:6"))
    ]


@pytest.mark.parametrize("failure_stage", ["reasoning", "append"])
async def test_a_failed_turns_delivered_image_is_recorded_once_under_its_chat(
    runtime, monkeypatch, failure_stage
):
    """Before or after AfterReasoningCtx, the image never rides a later reply."""
    _ = ExternalPushSyncService(
        live_turn_pushes=current_turn_pushes,
        session_manager=runtime.manager,
        event_bus=runtime.bus,
    )
    runtime.push.register_channel("qq", image=AsyncMock(return_value=None))
    original_append = runtime.manager.append_messages
    commits = []

    async def append(*args, **kwargs):
        # Only the turn's commit fails; recording the abandoned push goes through.
        commits.append(args)
        if len(commits) == 1:
            raise OSError("commit failed")
        return await original_append(*args, **kwargs)

    async def failing_turn(**_kwargs):
        assert "已发送" in await runtime.call(
            channel="qq", chat_id="gqq:6", image="scene.png"
        )
        if failure_stage == "reasoning":
            raise RuntimeError("turn failed")
        # Fails the commit, after AfterReasoningCtx.
        monkeypatch.setattr(runtime.manager, "append_messages", append)
        return reply()

    operation = runtime.pipeline(failing_turn).run(
        incoming(), runtime.session.key, dispatch_outbound=False
    )
    if failure_stage == "append":
        with pytest.raises(OSError, match="commit failed"):
            await operation
        assert len(commits) == 2
        monkeypatch.setattr(runtime.manager, "append_messages", original_append)
    else:
        await operation

    async def next_turn(**_kwargs):
        return reply()

    await runtime.pipeline(next_turn).run(
        incoming(), runtime.session.key, dispatch_outbound=False
    )

    stored = runtime.manager._store.fetch_session_messages(runtime.session.key)
    assert [
        (row["content"], row.get("media"), row["thread_id"])
        for row in stored
        if row["role"] == "assistant"
    ] == [
        ("", ["scene.png"], network_thread_id("mira", "qq", "gqq:6")),
        ("done", None, network_thread_id("mira", "qqbot", "friend")),
    ]


async def test_a_failure_to_record_abandoned_pushes_never_replaces_the_turns_error(
    runtime, monkeypatch
):
    _ = ExternalPushSyncService(
        live_turn_pushes=current_turn_pushes,
        session_manager=runtime.manager,
        event_bus=runtime.bus,
    )
    runtime.push.register_channel("qq", text=AsyncMock(return_value=None))
    turn_error = OSError("commit failed")
    append = AsyncMock(
        side_effect=[turn_error, OSError("record 1"), OSError("record 2")]
    )

    async def reasoning(**_kwargs):
        for text in ("one", "two"):
            assert "已发送" in await runtime.call(
                channel="qq", chat_id="gqq:6", message=text
            )
        monkeypatch.setattr(runtime.manager, "append_messages", append)
        return reply()

    with pytest.raises(OSError) as raised:
        await runtime.pipeline(reasoning).run(
            incoming(), runtime.session.key, dispatch_outbound=False
        )

    assert raised.value is turn_error
    assert raised.value.__notes__ == ["另有 2 条回合内已送达的推送未能记录"]
    # Both records were attempted after the commit failed.
    assert append.await_count == 3
