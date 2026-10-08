"""Passive turns own same-role desktop pushes until their ordered SQL commit."""

from core.compaction import CompactionController, CompactionFailedError
from core.compaction_summary import WorkingSummaryWriter

import asyncio
import json
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
from agent.provider import LLMResponse, ToolCall
from agent.tool_hooks import ToolExecutionRequest
from agent.tool_hooks.executor import ToolExecutor
from agent.tools.message_push import MessagePushTool
from agent.tools.registry import ToolRegistry
from bus.event_bus import EventBus
from shiori_sdk.messages import InboundMessage
from agent.turns.turn_pushes import current_turn_pushes
from conversation.push_sync import ExternalPushSyncService
from conversation.service import desktop_thread_id, scheduler_thread_id
from shiori_sdk.channels.threads import network_thread_id
from shiori_sdk.accounts.models import AccountRecord
from core.identity import IdentityChat, UserIdentityStore
from core.roles import RoleStore
from core.roles.reply_state import AffectionChange, RoleReply
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

    def pipeline(reasoning, *, relationship_runtime=None, outbound_port=None):
        return PassiveTurnPipeline(
            AgentCoreDeps(
                session=SimpleNamespace(
                    session_manager=manager,
                    presence=None,
                    relationship_runtime=relationship_runtime,
                ),
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
                outbound_port=outbound_port,
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
    from agent.provider import LLMProvider
    from agent.prompting.input_budget import BudgetPolicy

    provider = LLMProvider(
        api_key="test",
        model_context_window=input_token_threshold + 8192,
        default_max_tokens=8192,
        budget_policy=BudgetPolicy(safety_margin_tokens=0),
    )
    reasoner = DefaultReasoner(
        llm=LLMServices(provider=provider, light_provider=provider),
        llm_config=LLMConfig(),
        tools=ToolRegistry(),
        discovery=ToolDiscoveryState(),
        tool_search_enabled=False,
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
        )
    )
    return pipeline, reasoner


@pytest.mark.parametrize("summary", [False, True])
@pytest.mark.parametrize("retry_failure", ["empty", "request"])
async def test_empty_reply_failure_reports_diagnostics_without_committing_role_reply(
    tmp_path, retry_failure, summary, caplog
):
    manager = SessionManager(tmp_path)
    session = manager.get_or_create("role:mira")
    session.metadata["role_id"] = "mira"
    manager.save(session)
    pipeline, reasoner = _isolation_pipeline(manager)
    # Restore the real reasoning loop while retaining deterministic prompt setup.
    reasoner.run = DefaultReasoner.run.__get__(reasoner)
    provider = AsyncMock()
    responses = [
        LLMResponse(
            content="",
            thinking="secret thought",
            model="role-model",
            stream=True,
            finish_reason="length",
            total_tokens=128,
        ),
        (
            LLMResponse(
                content='{"content":" ","mood":"平静","thought":"private"}',
                model="role-model",
                stream=True,
                finish_reason="stop",
                total_tokens=10,
            )
            if retry_failure == "empty"
            else RuntimeError("upstream api_key=super-secret-key " + "x" * 10000)
        ),
    ]
    if summary:
        reasoner._llm_config = LLMConfig(max_iterations=1)
        responses.insert(
            0,
            LLMResponse(content="", tool_calls=[ToolCall("t1", "summary-trigger", {})]),
        )
    provider.chat.side_effect = responses
    reasoner._llm = LLMServices(provider=provider, light_provider=provider)
    failed_events = []
    pipeline._bus.observe = AsyncMock(side_effect=failed_events.append)
    with caplog.at_level("ERROR", logger="agent.core.passive_turn"):
        result = await pipeline.run(
            _turn(USER_DM), session.key, dispatch_outbound=False
        )
    assert result.content == "处理消息时出错，请稍后再试。"
    assert result.committed_message_id is None
    assert provider.chat.await_count == (3 if summary else 2)
    assert manager._store.fetch_session_messages(session.key) == []
    assert any(type(event).__name__ == "TurnFailed" for event in failed_events)
    records = [
        record
        for record in caplog.records
        if record.name == "agent.core.passive_turn"
        and "EmptyReplyError" in record.getMessage()
    ]
    assert len(records) == 1
    diagnostic_text = records[0].getMessage()
    assert "EmptyReplyError" in diagnostic_text
    payload = diagnostic_text.split("模型未产出有效正文。 ", 1)[1].split("\n", 1)[0]
    facts = json.loads(payload)
    assert facts["session"] == session.key
    assert facts["channel"] == "qq"
    assert facts["turn"]
    assert facts["retries"] == 1
    assert facts["attempts"][0]["model"] == "role-model"
    assert facts["attempts"][0]["stream"] is True
    assert facts["attempts"][0]["finish_reason"] == "length"
    assert facts["attempts"][0]["empty_kind"] == "raw_empty"
    if retry_failure == "empty":
        assert facts["outcome"] == "exhausted"
        assert facts["attempts"][1]["finish_reason"] == "stop"
        assert facts["attempts"][1]["empty_kind"] == "normalization_empty"
        assert facts["attempts"][1]["total_tokens"] == 10
    else:
        assert facts["outcome"] == "request_failed"
        assert facts["error_type"] == "RuntimeError"
        assert "upstream" in facts["error_summary"]
        assert len(facts["error_summary"]) <= 300
        assert "super-secret-key" not in diagnostic_text
    assert "secret thought" not in diagnostic_text
    assert "private" not in diagnostic_text


@pytest.mark.parametrize("summary", [False, True])
async def test_recovered_reply_commits_diagnostics_and_normal_content(
    tmp_path, summary
):
    manager = SessionManager(tmp_path)
    session = manager.get_or_create("role:mira")
    session.metadata["role_id"] = "mira"
    manager.save(session)
    pipeline, reasoner = _isolation_pipeline(manager)
    reasoner.run = DefaultReasoner.run.__get__(reasoner)
    provider = AsyncMock()
    responses = [
        LLMResponse(content="", total_tokens=11),
        LLMResponse(content="恢复正文", total_tokens=13),
        LLMResponse(content='{"mood":"平静","thought":"我想回应你。"}'),
    ]
    if summary:
        reasoner._llm_config = LLMConfig(max_iterations=1)
        responses.insert(
            0,
            LLMResponse(
                content="",
                tool_calls=[ToolCall("t1", "summary-trigger", {})],
                total_tokens=7,
            ),
        )
    provider.chat.side_effect = responses
    reasoner._llm = LLMServices(provider=provider, light_provider=provider)
    result = await pipeline.run(_turn(USER_DM), session.key, dispatch_outbound=False)
    assert result.content == "恢复正文"
    assert result.committed_message_id is not None
    persisted = SessionManager(tmp_path).get_or_create(session.key).messages
    assert persisted[-1]["content"] == "恢复正文"
    assert (
        persisted[-1]["metadata"]["context_retry"]["reply_recovery"]["outcome"]
        == "recovered"
    )
    assert persisted[-1]["metadata"]["context_retry"]["react_stats"][
        "total_tokens"
    ] == (31 if summary else 24)
    assert provider.chat.await_count == (4 if summary else 3)


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


async def test_bound_stranger_dm_only_adds_new_messages_after_binding(
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

    assert _labels(history) == ["desk", "udm"]
    assert not any("sdm-user" in text or "sdm-old" in text for text in history)
    # A fresh message from the newly bound private chat is shared next turn.
    reloaded = manager.get_or_create("role:mira")
    reloaded.add_message("user", "new-private-message", thread_id=STRANGER_DM)
    reloaded.add_message("assistant", "new-private-reply", thread_id=STRANGER_DM)
    manager.save(reloaded)
    history = await _model_history(tmp_path, DESKTOP)
    assert any("new-private-message" in text for text in history)
    assert not any("sdm-user" in text or "sdm-old" in text for text in history)


async def test_input_budget_counts_only_the_turn_context(memory_harness, monkeypatch):
    h = memory_harness
    _bind(h.manager.workspace, "902")
    _seed_role_session(h.manager, group_text="x" * 40000)
    monkeypatch.setattr(
        "agent.core.passive_turn.reasoning_loop.fetch_role_mood",
        AsyncMock(return_value=None),
    )

    for thread, runs in ((DESKTOP, True), (GROUP_B, True), (GROUP_A, False)):
        pipeline, reasoner = _isolation_pipeline(h.manager, input_token_threshold=2000)
        # Exercise the real unified guard instead of replacing the entire loop.
        reasoner.run = DefaultReasoner.run.__get__(reasoner, DefaultReasoner)
        provider = reasoner._llm.provider
        provider.chat = AsyncMock(return_value=LLMResponse(content="ok"))
        reasoner._compaction = CompactionController(
            h.manager,
            h.maintenance,
            WorkingSummaryWriter(h.manager, provider, "controlled", 2000),
        )
        try:
            if runs:
                await pipeline.run(_turn(thread), "role:mira", dispatch_outbound=False)
            else:
                with pytest.raises(CompactionFailedError) as caught:
                    await pipeline.run(
                        _turn(thread), "role:mira", dispatch_outbound=False
                    )
                # Group A's own source is truncated into one in-budget summary
                # request; the stub reply is not a valid summary.
                assert caught.value.result.failure_stage == "summary"
                assert caught.value.result.memory_committed
            assert provider.chat.await_count == 1
        finally:
            await provider.aclose()
    from conversation.context_scope import history_start, turn_context_view

    session = h.manager.get_or_create("role:mira")
    for thread in (DESKTOP, GROUP_B, GROUP_A):
        assert (
            history_start(
                session, turn_context_view(h.manager.workspace, "mira", thread)
            )
            == 0
        )


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


async def test_a_failed_affection_write_never_blocks_the_committed_replys_delivery(
    runtime,
):
    relationship = SimpleNamespace(
        enrich_session_metadata=lambda metadata: metadata,
        handle_user_message=Mock(),
        apply_turn_affection=AsyncMock(side_effect=OSError("affection disk full")),
    )
    port = SimpleNamespace(dispatch=AsyncMock())

    async def reasoning(**_kwargs):
        assert "已排队" in await runtime.call(message="first")
        result = reply()
        result.role_reply = RoleReply(
            content="done",
            mood="平静",
            thought="完成了",
            affection=AffectionChange(1, "他来找我了。"),
        )
        result.role_reply_mood_fresh = True
        return result

    msg = incoming()
    msg.metadata["sender_is_user"] = True
    with pytest.raises(OSError, match="affection disk full"):
        await runtime.pipeline(
            reasoning, relationship_runtime=relationship, outbound_port=port
        ).run(msg, runtime.session.key, dispatch_outbound=True)

    relationship.apply_turn_affection.assert_awaited_once()
    # The reply and its push were delivered, and the push is stored only once.
    assert [call.args[0].content for call in port.dispatch.await_args_list] == ["done"]
    assert [row["content"] for row in runtime.emitted[0]["payload"]["messages"]] == [
        "first"
    ]
    stored = runtime.manager._store.fetch_session_messages(runtime.session.key)
    assert [row["content"] for row in stored] == ["send to desktop", "first", "done"]
