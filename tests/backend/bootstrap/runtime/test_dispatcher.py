"""Background result turns select the published generation at delivery time."""

from dataclasses import replace
from unittest.mock import AsyncMock
import asyncio
from types import SimpleNamespace
import pytest

from agent.config_models import Config
from bootstrap.app import AppRuntime, RuntimeFeatures
from bootstrap.runtime.dispatcher import RuntimeDispatcher
from bootstrap.runtime.generations import RuntimeCandidate
from bus.queue import MessageBus
from shiori_sdk.messages import InboundMessage
from shiori_sdk.messages import DeliveryOutcome
from contextlib import asynccontextmanager
from core.channels import ChannelHub
from core.roles import RoleAggregateService
from shiori_sdk.accounts.models import AccountResponseRules
from agent.provider import LLMResponse, ToolCall
from tests.support.external_turns import ExternalTurnHost
from tests.support.chat_replies import chat_reply
from session.manager import SessionManager


async def proactive_task(
    env,
    tmp_path,
    *,
    addressed=False,
    topic=None,
    stage="pacing",
    failure=None,
    failure_at=2,
    channel="qq",
    target_id="room",
    desktop=False,
    draft_messages=None,
    correction_response=None,
    invalidate_draft=False,
):
    """A real proactive draft tool loop, account receipt ledger and role dispatcher."""
    from agent.account_delivery import AccountDelivery
    from agent.tools.account_delivery import AccountSendTool
    from agent.turns.orchestrator import TurnOrchestrator, TurnOrchestratorDeps
    from agent.turns.outbound import DeliveryReceipt
    from agent.looping.ports import SessionServices
    from bus.events_lifecycle import ProactiveMessageCommitted
    from conversation.service import ConversationService, desktop_thread_id
    from core.accounts.delivery_ledger import AccountDeliveryLedger
    from core.common.runtime_scope import bind_runtime
    from core.identity import UserIdentityStore
    from proactive_v2.tools import ToolDeps
    from tests.backend.proactive_v2.conftest import make_proactive_pipeline, FakeLLM

    sent, events = [], []
    event_bus = env.host.loop._event_bus
    event_bus.on(ProactiveMessageCommitted, events.append)

    async def resolve(payload):
        if stage == "retarget":
            env.started.set()
            await env.release.wait()
        return {
            "channel": channel,
            "chat_id": (
                "gqq:" + payload["target_id"]
                if channel == "qq"
                else payload["target_id"]
            ),
            "chat_type": "group",
            "message_thread_id": payload.get("message_thread_id"),
        }

    async def send(payload):
        sent.append(payload)
        if stage == "sending" and len(sent) == 1:
            env.started.set()
            await env.release.wait()
        if failure is not None and len(sent) == failure_at:
            raise failure
        return {"message_id": f"proactive-{len(sent)}"}

    rpc = SimpleNamespace(
        resolve=lambda name: (
            channel,
            resolve if name.endswith("account.resolve") else send,
        )
    )
    delivery = AccountDelivery(
        env.host.roles.accounts,
        rpc,
        AccountDeliveryLedger(tmp_path),
        UserIdentityStore(tmp_path),
    )
    env.host.loop.tools.register(AccountSendTool(delivery, event_bus))

    async def desktop_send(message):
        await send({"message": message.content})
        return DeliveryReceipt.sent()

    owner = TurnOrchestrator(
        TurnOrchestratorDeps(
            session=SessionServices(
                env.host.manager,
                conversation_service=ConversationService(env.host.manager),
            ),
            outbound=SimpleNamespace(dispatch=desktop_send),
            event_bus=event_bus,
            account_delivery=delivery,
            role_lookup=env.host.roles.get_role,
        )
    )
    llm = FakeLLM(
        [
            ("get_recent_chat", {}),
            (
                "message_push",
                {
                    "messages": (
                        ["主动前缀", "主动尾段"]
                        if draft_messages is None
                        else draft_messages
                    ),
                    "mood": "平静",
                    "thought": "我想和你说说。",
                    "evidence": [],
                    **(
                        {
                            "account_channel": channel,
                            "target_kind": "group",
                            "target_id": target_id,
                            "mention_ids": ["alice"] if addressed else [],
                            **({"message_thread_id": topic} if topic else {}),
                        }
                        if not desktop
                        else {}
                    ),
                },
            ),
            ("finish_turn", {"decision": "reply"}),
        ]
    )

    corrections = []

    async def provider_chat(**kwargs):
        if [t["function"]["name"] for t in kwargs["tools"]] == ["finish_reply"]:
            corrections.append(kwargs)
            assert correction_response is not None
            return correction_response
        if stage == "generation" and not llm.calls:
            env.started.set()
            await env.release.wait()
        call = await llm(kwargs["messages"], kwargs["tools"], kwargs["tool_choice"])
        assert call is not None
        if invalidate_draft and call["name"] == "message_push":
            from agent.turns.reply_interruption import current_reply_interruption

            interruption = current_reply_interruption()
            assert interruption is not None
            interruption.invalidate()
        return LLMResponse(
            content="",
            tool_calls=[
                ToolCall(f"proactive-{len(llm.calls)}", call["name"], call["input"])
            ],
        )

    from proactive_v2.agent_tick_factory import AgentTickDeps, AgentTickFactory

    model = AgentTickFactory(
        AgentTickDeps(
            cfg=None,
            sense=None,
            presence=None,
            provider=SimpleNamespace(chat=provider_chat),
            model="test",
            max_tokens=2048,
            memory=None,
            state_store=None,
            any_action_gate=None,
            passive_busy_fn=None,
            deduper=None,
            rng=None,
            workspace_context_fn=lambda: "",
            role_prompt_fn=lambda: "",
        )
    )._build_llm_fn()

    async def recent_chat(**_):
        if stage == "tool":
            env.started.set()
            await env.release.wait()
        return [{"role": "user", "content": "已执行的查询事实"}]

    pipeline = make_proactive_pipeline(
        session_key="role:mira",
        llm_fn=model,
        target_transport_fn=lambda: ("desktop", "role:mira"),
        tool_deps=ToolDeps(
            shared_tools=env.host.loop.tools,
            recent_chat_fn=recent_chat,
        ),
    )
    pipeline._turn_orchestrator = owner
    registry = env.host.loop.role_runtime_registry
    context = registry.create_context(
        role_id="mira",
        thread_id=desktop_thread_id("mira"),
        transport_channel="desktop",
        transport_chat_id="role:mira",
        source="proactive",
        work_kind="proactive_tick",
    )

    async def run():
        async with env.candidate.acquire() as lease:
            with bind_runtime(lease):
                return await registry.dispatch_proactive_tick(context, pipeline.run)

    task = asyncio.create_task(run())
    return SimpleNamespace(
        task=task,
        sent=sent,
        events=events,
        pipeline=pipeline,
        llm=llm,
        corrections=corrections,
    )


@pytest.mark.parametrize("correction_kind", ["valid", "business_tool", "invalidated"])
async def test_proactive_format_correction_never_replays_completed_work(
    tmp_path, monkeypatch, correction_kind
):
    from agent.core.passive_turn.natural_reply import NaturalReplyCorrectionError
    from session.manager.models import whole_session

    response = LLMResponse(
        "",
        [
            (
                ToolCall("correction", "public", {})
                if correction_kind == "business_tool"
                else ToolCall(
                    "correction",
                    "finish_reply",
                    {"messages": ["整理好了。", "后续细节"]},
                )
            )
        ],
    )
    async with natural_dispatcher(tmp_path, monkeypatch) as env:
        env.release.set()
        proactive = await proactive_task(
            env,
            tmp_path,
            draft_messages=[],
            correction_response=response,
            invalidate_draft=correction_kind == "invalidated",
        )
        if correction_kind == "business_tool":
            with pytest.raises(NaturalReplyCorrectionError):
                await proactive.task
        else:
            await proactive.task
        assert [m["message"] for m in proactive.sent] == (
            ["整理好了。", "后续细节"] if correction_kind == "valid" else []
        )
        assert len(proactive.corrections) == (
            0 if correction_kind == "invalidated" else 1
        )
        if proactive.corrections:
            request = proactive.corrections[0]
            assert request["call_purpose"] == "auxiliary"
            assert [t["function"]["name"] for t in request["tools"]] == ["finish_reply"]
            assert any("已执行的查询事实" in str(m) for m in request["messages"])
        rows = SessionManager(tmp_path).get_or_create("role:mira").messages
        facts = [m for m in rows if m.get("tool_chain")]
        assert len(facts) == 1
        assert [c["name"] for g in facts[0]["tool_chain"] for c in g["calls"]] == [
            "get_recent_chat"
        ]
        assert not env.tool_calls
        assert len(proactive.llm.calls) == (3 if correction_kind == "valid" else 2)
        assert len(proactive.events) == int(correction_kind == "valid")
        assert not any(
            "finish_reply" in str(m)
            for m in SessionManager(tmp_path)
            .get_or_create("role:mira")
            .get_history(include=whole_session)
        )


@pytest.mark.parametrize("stage", ["pacing", "sending"])
@pytest.mark.parametrize("addressed", [False, True])
async def test_admitted_group_request_stops_proactive_tail_at_safe_send_boundary(
    tmp_path, monkeypatch, stage, addressed
):
    async with natural_dispatcher(tmp_path, monkeypatch, stage=stage) as env:
        proactive = await proactive_task(
            env, tmp_path, addressed=addressed, stage=stage
        )
        await asyncio.wait_for(env.started.wait(), 3)
        await env.receive("补充", sender="alice" if addressed else "bob")
        await env.receive("继续补充", sender="alice" if addressed else "bob")
        await until(lambda: env.bus.inbound_size == 0)
        env.release.set()
        await asyncio.wait_for(proactive.task, 3)
        await until(lambda: env.candidate.references == 0)
        assert [m["message"] for m in proactive.sent] == ["主动前缀"]
        assert len(proactive.events) == 1
        assert proactive.events[0].assistant_response == "主动前缀"
        assert proactive.events[0].chat_id == "gqq:room"
        assert not proactive.pipeline._state_store._deliveries
        stored = SessionManager(tmp_path).get_or_create("role:mira")
        assert not any("主动尾段" in m["content"] for m in stored.messages)
        assert [
            m["content"]
            for m in stored.messages
            if m["content"] in {"补充", "继续补充"}
        ] == ["补充", "继续补充"]
        facts = [
            m for m in stored.messages if m.get("tool_chain") and m.get("proactive")
        ]
        assert len(facts) == 1
        assert facts[0]["tool_chain"][0]["calls"][0]["name"] == "get_recent_chat"
        assert len(proactive.llm.calls) == 3


@pytest.mark.parametrize(
    "input_options",
    [
        {"sender": "bob"},
        {"account": "two"},
        {"account": "three"},
        {"chat": "gqq:other"},
        {"chat_type": "private"},
        {"topic": "27"},
        {"sender": "blocked"},
        {"mentioned": False},
    ],
)
async def test_proactive_addressed_group_isolates_other_sender_origin_and_chatter(
    tmp_path, monkeypatch, input_options
):
    async with natural_dispatcher(tmp_path, monkeypatch) as env:
        proactive = await proactive_task(env, tmp_path, addressed=True)
        await asyncio.wait_for(env.started.wait(), 3)
        await env.receive("其他请求", **input_options)
        await until(lambda: env.bus.inbound_size == 0)
        assert not proactive.task.done()
        assert env.requests == []
        env.release.set()
        await asyncio.wait_for(proactive.task, 3)
        await until(lambda: env.candidate.references == 0)
        assert [m["message"] for m in proactive.sent] == ["主动前缀", "主动尾段"]
        assert len(proactive.events) == 1
        assert len(proactive.pipeline._state_store._deliveries) == 1
        assert proactive.sent[0]["mention_ids"] == ["alice"]
        assert proactive.sent[1]["mention_ids"] == []


async def test_proactive_telegram_topic_does_not_cancel_other_batch(
    tmp_path, monkeypatch
):
    async with natural_dispatcher(tmp_path, monkeypatch) as env:
        proactive = await proactive_task(
            env, tmp_path, channel="telegram", target_id="-42", topic=27
        )
        await asyncio.wait_for(env.started.wait(), 3)
        unrelated = await env.receive(
            "别的话题", channel="telegram", chat="-42", topic="28"
        )
        assert unrelated is not None
        await until(lambda: env.bus.inbound_size == 0)
        assert not proactive.task.done()
        await env.receive(
            "当前话题的有效请求", channel="telegram", chat="-42", topic="27"
        )
        await until(lambda: env.bus.inbound_size == 0)
        env.release.set()
        await asyncio.wait_for(proactive.task, 3)
        await until(lambda: env.candidate.references == 0)
        assert [m["message"] for m in proactive.sent] == ["主动前缀"]
        assert proactive.sent[0]["message_thread_id"] == 27


async def test_proactive_duplicate_input_is_rejected_before_invalidating_batch(
    tmp_path, monkeypatch
):
    async with natural_dispatcher(tmp_path, monkeypatch) as env:
        env.release.set()
        await env.receive("already-stored", external_id="platform-original")
        await until(lambda: env.candidate.references == 0)
        env.release.clear()
        env.started.clear()
        proactive = await proactive_task(env, tmp_path)
        await asyncio.wait_for(env.started.wait(), 3)
        duplicate = await env.receive("duplicate-copy", external_id="platform-original")
        assert duplicate is not None and duplicate.metadata["conversation_duplicate"]
        await until(lambda: env.bus.inbound_size == 0)
        assert not proactive.task.done()
        env.release.set()
        await proactive.task
        assert [m["message"] for m in proactive.sent] == ["主动前缀", "主动尾段"]
        assert len(env.requests) == 1


async def test_request_accepted_during_proactive_target_resolution_invalidates_new_target(
    tmp_path, monkeypatch
):
    async with natural_dispatcher(tmp_path, monkeypatch) as env:
        proactive = await proactive_task(env, tmp_path, stage="retarget")
        await asyncio.wait_for(env.started.wait(), 3)
        await env.receive("目标解析期间的有效补充")
        await until(lambda: env.bus.inbound_size == 0)
        env.release.set()
        await proactive.task
        await until(lambda: env.candidate.references == 0)
        assert proactive.sent == []
        assert len(proactive.llm.calls) == 2


async def test_addressed_proactive_supplement_stops_before_other_sender_fifo(
    tmp_path, monkeypatch
):
    async with natural_dispatcher(tmp_path, monkeypatch) as env:

        async def single_reply(**kwargs):
            if kwargs.get("response_format"):
                return LLMResponse(content='{"mood":"平静","thought":"我想继续聊。"}')
            env.requests.append(kwargs)
            return chat_reply(
                [f"reply-{len(env.requests)}"], tools=kwargs.get("tools", [])
            )

        monkeypatch.setattr(env.host.provider, "chat", single_reply)
        proactive = await proactive_task(env, tmp_path, addressed=True)
        await asyncio.wait_for(env.started.wait(), 3)
        await env.receive("bob-first", sender="bob")
        await env.receive("alice-later", sender="alice")
        await until(lambda: env.candidate.references == 0 and env.bus.inbound_size == 0)
        await proactive.task
        assert not env.release.is_set()
        assert [m["message"] for m in proactive.sent] == ["主动前缀"]
        assert [
            m["content"]
            for m in SessionManager(tmp_path).get_or_create("role:mira").messages
            if m["content"] in {"bob-first", "alice-later"}
        ] == ["bob-first", "alice-later"]


@pytest.mark.parametrize("failure_at", [1, 2])
@pytest.mark.parametrize("unknown", [False, True, "native_timeout"])
async def test_proactive_failed_or_unknown_send_stops_without_retry_and_keeps_only_receipts(
    tmp_path, monkeypatch, failure_at, unknown
):
    from shiori_sdk.accounts.targets import UncertainDeliveryError
    from session.manager.models import whole_session

    failure = (
        TimeoutError("channel request deadline")
        if unknown == "native_timeout"
        else (
            UncertainDeliveryError("lost receipt") if unknown else ValueError("refused")
        )
    )
    async with natural_dispatcher(tmp_path, monkeypatch) as env:
        env.release.set()
        proactive = await proactive_task(
            env, tmp_path, failure=failure, failure_at=failure_at
        )
        with pytest.raises(type(failure), match=str(failure)):
            await proactive.task
        assert len(proactive.sent) == failure_at
        assert not proactive.pipeline._state_store._deliveries
        assert len(proactive.events) == failure_at - 1
        session = SessionManager(tmp_path).get_or_create("role:mira")
        rows = [m for m in session.messages if m.get("delivery_status")]
        assert [m["delivery_status"] for m in rows] == (
            ["sent"] if failure_at == 2 else []
        ) + ["uncertain" if unknown else "failed"]
        shown = [
            m["content"]
            for m in session.get_history(include=whole_session)
            if m["role"] == "assistant"
        ]
        assert ("主动前缀" in shown) == (failure_at == 2)
        assert "主动尾段" not in shown


@pytest.mark.parametrize("change", ["generation_stop", "role_flag_off"])
async def test_proactive_runtime_retirement_or_flag_disable_never_sends_old_tail(
    tmp_path, monkeypatch, change
):
    async with natural_dispatcher(tmp_path, monkeypatch) as env:
        proactive = await proactive_task(env, tmp_path)
        await asyncio.wait_for(env.started.wait(), 3)
        if change == "generation_stop":
            env.candidate.reply_sequences.stop()
        else:
            env.host.roles.update_role(
                "mira", runtime_config={"natural_chat_enabled": False}
            )
        env.release.set()
        await asyncio.wait_for(proactive.task, 3)
        assert [m["message"] for m in proactive.sent] == ["主动前缀"]
        assert not env.candidate.reply_sequences._background


@pytest.mark.parametrize("stage", ["generation", "tool", "pacing", "sending"])
async def test_desktop_supplements_stop_proactive_work_and_publish_only_committed_prefix(
    tmp_path, monkeypatch, stage
):
    from conversation.service import ConversationService
    from conversation.listening import GroupListeningControl
    from desktop_bridge.service import DesktopBridgeService
    from core.common.runtime_scope import bind_runtime

    async with natural_dispatcher(tmp_path, monkeypatch, stage=stage) as env:
        bridge = DesktopBridgeService(
            workspace=tmp_path,
            role_store=env.host.roles,
            session_manager=env.host.manager,
            agent_loop=env.host.loop,
            event_bus=env.host.loop._event_bus,
            group_environment=env.host.group_environment,
            group_listening=GroupListeningControl(
                ConversationService(env.host.manager), lambda _: False
            ),
        )
        emitted = []
        bridge.add_event_listener(emitted.append)
        try:
            proactive = await proactive_task(env, tmp_path, desktop=True, stage=stage)
            await asyncio.wait_for(env.started.wait(), 3)
            async with env.candidate.acquire() as lease:
                with bind_runtime(lease):
                    for turn in ("supplement-1", "supplement-2"):
                        response = await bridge.handle(
                            {
                                "id": turn,
                                "method": "chat.send",
                                "payload": {"role_id": "mira", "content": turn},
                            },
                            emit_event=emitted.append,
                        )
                        assert response.error is None
            env.release.set()
            await asyncio.wait_for(proactive.task, 3)
            await asyncio.wait_for(
                bridge.chat_service._tasks_by_session["role:mira"].task, 3
            )
            session = SessionManager(tmp_path).get_or_create("role:mira")
            assert [m["message"] for m in proactive.sent] == (
                ["主动前缀"] if stage in {"pacing", "sending"} else []
            )
            assert [
                m["content"]
                for m in session.messages
                if m["content"].startswith("supplement-")
            ] == ["supplement-1", "supplement-2"]
            assert not any("主动尾段" in m["content"] for m in session.messages)
            facts = [
                m
                for m in session.messages
                if m.get("proactive") and m.get("tool_chain")
            ]
            assert len(facts) == (0 if stage == "generation" else 1)
            if stage in {"generation", "tool"}:
                assert len(proactive.llm.calls) == 1
            assert any(
                e["method"] == "chat.done" and e["payload"]["turn_id"] == "supplement-2"
                for e in emitted
            )
            if proactive.sent:
                persisted_prefix = next(
                    m for m in session.messages if m["content"] == "主动前缀"
                )
                assert any(
                    e["method"] == "session.updated"
                    and e["payload"].get("message", {}).get("id")
                    == persisted_prefix["id"]
                    for e in emitted
                )
        finally:
            env.release.set()
            await bridge.aclose()


@pytest.mark.parametrize("stage", ["generation", "tool"])
async def test_proactive_outer_shutdown_finishes_started_step_without_next_tool(
    tmp_path, monkeypatch, stage
):
    async with natural_dispatcher(tmp_path, monkeypatch, stage=stage) as env:
        proactive = await proactive_task(env, tmp_path, desktop=True, stage=stage)
        await asyncio.wait_for(env.started.wait(), 3)
        env.candidate.reply_sequences.stop()
        proactive.task.cancel()
        await asyncio.sleep(0)
        assert not proactive.task.done()
        env.release.set()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(proactive.task, 3)
        assert proactive.sent == []
        assert len(proactive.llm.calls) == 1
        rows = SessionManager(tmp_path).get_or_create("role:mira").messages
        facts = [m for m in rows if m.get("tool_chain") and m.get("proactive")]
        assert len(facts) == (1 if stage == "tool" else 0)


@pytest.mark.parametrize("stage", ["generation", "tool", "pacing"])
@pytest.mark.parametrize(
    "channel,chat,topic", [("qq", "gqq:room", ""), ("telegram", "-42", "27")]
)
async def test_spawn_report_uses_original_role_account_topic_and_keeps_completed_facts(
    tmp_path, monkeypatch, stage, channel, chat, topic
):
    from agent.background.subagent_manager import SubagentManager
    from session.manager.models import whole_session

    async with natural_dispatcher(tmp_path, monkeypatch, stage=stage) as env:
        env.release.set()
        origin = await env.receive(
            "请后台整理", channel=channel, chat=chat, topic=topic
        )
        await until(lambda: env.candidate.references == 0)
        env.release.clear()
        env.started.clear()
        env.tool_calls.clear()
        replies = []

        async def model(**kwargs):
            if kwargs.get("response_format"):
                return LLMResponse(content='{"mood":"平静","thought":"我想说明结果。"}')
            number = len(replies)
            replies.append(kwargs)
            if number == 0 and stage == "generation":
                env.started.set()
                await env.release.wait()
            if number == 0 and stage == "tool":
                return LLMResponse(
                    content="尚未展示的工具前言",
                    tool_calls=[
                        ToolCall("completed-tool", "public", {}),
                        ToolCall("unstarted-tool", "public", {}),
                    ],
                )
            return chat_reply(
                ["回报前缀", "回报尾段"] if number == 0 else ["结合补充的新回复"],
                tools=kwargs.get("tools", []),
            )

        monkeypatch.setattr(env.host.provider, "chat", model)
        producer = SubagentManager(
            provider=env.host.provider,
            workspace=tmp_path,
            bus=env.bus,
            model="test",
            max_tokens=256,
            fetch_requester=object(),
        )
        run_job = AsyncMock(return_value="完成的后台原始结果，不得重跑")
        monkeypatch.setattr(
            producer,
            "_build_subagent",
            lambda **_: SimpleNamespace(
                run=run_job, last_exit_reason="completed", last_usage={}
            ),
        )
        assert origin is not None
        await producer.spawn(
            task="整理资料",
            label="资料",
            origin_channel=channel,
            origin_chat_id=chat,
            role_id="mira",
            origin=origin,
        )
        await producer.drain()
        await asyncio.wait_for(env.started.wait(), 3)
        await env.receive("补充要求", channel=channel, chat=chat, topic=topic)
        await until(lambda: env.bus.inbound_size == 0)
        env.release.set()
        await until(lambda: env.candidate.references == 0)
        run_job.assert_awaited_once_with("整理资料")
        rows = SessionManager(tmp_path).get_or_create("role:mira").messages
        assert not any("回报尾段" in m["content"] for m in rows)
        assert not any(
            m["role"] == "user" and m["content"].startswith("[后台") for m in rows
        )
        completion_facts = [
            call
            for row in rows
            for group in row.get("tool_chain", [])
            for call in group["calls"]
            if call["name"] == "spawn"
        ]
        assert len(completion_facts) == 1
        assert completion_facts[0]["result"] == "完成的后台原始结果，不得重跑"
        assert env.tool_calls == (["executed"] if stage == "tool" else [])
        result_rows = [m for m in rows if m["content"] == "回报前缀"]
        assert len(result_rows) == (1 if stage == "pacing" else 0)
        if result_rows:
            metadata = result_rows[0]["metadata"]
            assert metadata["account_id"] == origin.metadata["account_id"]
            assert str(metadata["message_thread_id"]) == topic
        history = (
            SessionManager(tmp_path)
            .get_or_create("role:mira")
            .get_history(include=whole_session)
        )
        assert (
            sum(m.get("content") == "完成的后台原始结果，不得重跑" for m in history)
            == 1
        )
        assert all("回报尾段" not in str(m.get("content")) for m in history)


async def until(predicate):
    async def wait():
        while not predicate():
            await asyncio.sleep(0)

    await asyncio.wait_for(wait(), 3)


@asynccontextmanager
async def natural_dispatcher(tmp_path, monkeypatch, *, stage="pacing", enabled=True):
    """Real admission, dispatcher, role gate, reasoner, bus acknowledgements and DB."""
    host = ExternalTurnHost(tmp_path)
    host.roles.update_role("mira", runtime_config={"natural_chat_enabled": enabled})
    host.roles.create_role(
        role_id="other",
        name="Other",
        system_prompt="test",
        runtime_config={"natural_chat_enabled": enabled},
    )
    bus = MessageBus()
    host.loop.bus = bus
    host.loop._agent_core.pipeline._outbound_port._bus = bus
    service = RoleAggregateService.from_runtime(
        workspace=tmp_path, role_store=host.roles, session_manager=host.manager
    )
    hub = ChannelHub(service)
    accounts = {}
    for channel, suffix, role in (
        ("qq", "one", "mira"),
        ("qq", "two", "mira"),
        ("telegram", "one", "mira"),
        ("qq", "three", "other"),
    ):
        record = host.roles.accounts.register(
            plugin_id=channel + ("_alternative" if suffix == "two" else ""),
            platform=channel,
            platform_account_id=suffix,
            config_ref=suffix,
            token="live",
            role_id=role,
            response_rules=AccountResponseRules(
                group_enabled=True, blocked_sender_ids=("blocked",)
            ),
        )
        host.roles.accounts.report(record.record.id, "live", connection="online")
        accounts[(channel, suffix)] = record.record.id
    started, release = asyncio.Event(), asyncio.Event()
    sent, requests, tool_calls = [], [], []
    running = 0
    max_running = 0

    async def model(**kwargs):
        nonlocal running, max_running
        if kwargs.get("response_format"):
            return LLMResponse(content='{"mood":"平静","thought":"我想继续聊。"}')
        running += 1
        max_running = max(running, max_running)
        number = len(requests)
        requests.append(kwargs)
        try:
            if not number and stage == "generation":
                started.set()
                await release.wait()
            if not number and stage == "tool":
                return LLMResponse(
                    content="private tool preamble",
                    tool_calls=[
                        ToolCall("first-tool", "public", {}),
                        ToolCall("must-not-run", "public", {}),
                    ],
                )
            return chat_reply(
                ["prefix", "tail"] if not number else [f"next-{number}"],
                tools=kwargs.get("tools", []),
                plain_content=(
                    "prefix\n<message-break/>\ntail" if not number else f"next-{number}"
                ),
            )
        finally:
            running -= 1

    monkeypatch.setattr(host.provider, "chat", model)

    async def execute(**kwargs):
        tool_calls.append("executed")
        started.set()
        await release.wait()
        return "durable tool fact"

    monkeypatch.setattr(host.loop.tools.get_tool("public"), "execute", execute)

    async def pause(_):
        if stage == "pacing":
            started.set()
            await release.wait()

    monkeypatch.setattr("agent.turns.reply_sequence.wait_between_messages", pause)

    async def send(message):
        sent.append(message)
        if len(sent) == 1 and stage == "sending":
            started.set()
            await release.wait()
        message.delivery_outcome = DeliveryOutcome("sent", f"sent-{len(sent)}")

    for channel in ("qq", "telegram"):
        bus.subscribe_outbound(channel, send, supports_reply_sequence=True)
    candidate = RuntimeCandidate(
        1,
        SimpleNamespace(
            loop=host.loop, role_runtime_registry=host.loop.role_runtime_registry
        ),
        SimpleNamespace(),
    )
    bus.bind_runtime_admission(candidate.acquire)
    app = SimpleNamespace(
        bus=bus, wait_for_admission=AsyncMock(), acquire=candidate.acquire
    )
    inbound = asyncio.create_task(RuntimeDispatcher(app).run())
    outbound = asyncio.create_task(bus.dispatch_outbound())

    async def receive(
        text,
        *,
        sender="alice",
        chat="gqq:room",
        channel="qq",
        account="one",
        chat_type="group",
        mentioned=True,
        external_id=None,
        topic="",
    ):
        message = InboundMessage(
            channel,
            sender,
            chat,
            text,
            metadata={
                "account_id": accounts[channel, account],
                "chat_type": chat_type,
                "mentioned": mentioned,
                "external_message_id": external_id or text,
                "message_thread_id": topic,
            },
        )
        routed = hub.route_account_inbound(message)
        if routed is not None:
            await bus.publish_inbound(routed)
        return routed

    try:
        yield SimpleNamespace(
            host=host,
            bus=bus,
            candidate=candidate,
            receive=receive,
            started=started,
            release=release,
            sent=sent,
            requests=requests,
            tool_calls=tool_calls,
            max_running=lambda: max_running,
        )
    finally:
        release.set()
        inbound.cancel()
        await asyncio.gather(inbound, return_exceptions=True)
        outbound.cancel()
        await asyncio.gather(outbound, return_exceptions=True)
        await host.loop._event_bus.aclose()


@pytest.mark.parametrize("stage", ["pacing", "generation", "sending"])
@pytest.mark.parametrize("chat_type", ["private", "group"])
async def test_admitted_supplements_stop_only_unsent_reply_and_keep_all_input(
    tmp_path, monkeypatch, stage, chat_type
):
    async with natural_dispatcher(tmp_path, monkeypatch, stage=stage) as env:
        await env.receive("first", chat_type=chat_type)
        await asyncio.wait_for(env.started.wait(), 3)
        await env.receive("second", chat_type=chat_type)
        await env.receive("third", chat_type=chat_type)
        await until(lambda: env.bus.inbound_size == 0)
        if stage == "sending":
            assert env.candidate.references > 0
            assert [m.content for m in env.sent] == ["prefix"]
        env.release.set()
        await until(lambda: env.candidate.references == 0)
        assert "tail" not in [m.content for m in env.sent]
        assert (
            "prefix" in [m.content for m in env.sent]
            if stage != "generation"
            else not any(m.content == "prefix" for m in env.sent)
        )
        session = SessionManager(tmp_path).get_or_create("role:mira")
        assert [
            m["content"]
            for m in session.messages
            if m["role"] == "user" and m["content"] in ("first", "second", "third")
        ] == ["first", "second", "third"]
        assert not any("tail" in m["content"] for m in session.messages)
        assert env.max_running() == 1
        assert env.candidate.reply_sequences._replies == {}


@pytest.mark.parametrize(
    "change",
    [
        "sender",
        "chat",
        "account",
        "channel",
        "role",
        "topic",
        "chat_type",
        "sidechat",
        "blacklist",
        "duplicate",
    ],
)
async def test_group_admission_and_exact_origin_do_not_cancel_other_reply(
    tmp_path, monkeypatch, change
):
    async with natural_dispatcher(tmp_path, monkeypatch) as env:
        await env.receive("first", channel="telegram" if change == "topic" else "qq")
        await asyncio.wait_for(env.started.wait(), 3)
        changes = {
            "sender": {"sender": "bob"},
            "chat": {"chat": "gqq:other"},
            "account": {"account": "two"},
            "channel": {"channel": "telegram"},
            "role": {"account": "three"},
            "topic": {"channel": "telegram", "topic": "42"},
            "chat_type": {"chat_type": "private"},
            "sidechat": {"mentioned": False},
            "blacklist": {"sender": "blocked"},
            "duplicate": {"external_id": "first"},
        }
        await env.receive("second", **changes[change])
        await until(lambda: env.bus.inbound_size == 0)
        if change in ("sender", "sidechat", "blacklist", "duplicate"):
            assert len(env.requests) == 1
        else:
            # Other receiving chats may generate while the first chat paces.
            await until(lambda: len(env.requests) == 2)
        env.release.set()
        await until(lambda: env.candidate.references == 0)
        assert [m.content for m in env.sent if m.content in ("prefix", "tail")] == [
            "prefix",
            "tail",
        ]
        expected = 1 if change in ("sidechat", "blacklist", "duplicate") else 2
        assert len(env.requests) == expected
        assert env.max_running() == 1


async def test_inflight_duplicate_does_not_invalidate_generation(tmp_path, monkeypatch):
    async with natural_dispatcher(tmp_path, monkeypatch, stage="generation") as env:
        await env.receive("first")
        await asyncio.wait_for(env.started.wait(), 3)
        await env.receive("replayed", external_id="first")
        await until(lambda: env.bus.inbound_size == 0)
        env.release.set()
        await until(lambda: env.candidate.references == 0)
        assert [m.content for m in env.sent] == ["prefix", "tail"]
        assert len(env.requests) == 1


async def test_current_group_sender_cuts_pause_before_other_senders_fifo_requests(
    tmp_path, monkeypatch
):
    async with natural_dispatcher(tmp_path, monkeypatch) as env:
        await env.receive("alice-first")
        await asyncio.wait_for(env.started.wait(), 3)
        await env.receive("bob-request", sender="bob")
        await env.receive("alice-supplement")
        # The first pacing wait remains blocked forever. Admission must cancel
        # it before awaiting that chat's tail, so both queued requests can run.
        await until(lambda: env.bus.inbound_size == 0 and env.candidate.references == 0)
        assert not env.release.is_set()
        assert [message.content for message in env.sent] == [
            "prefix",
            "next-1",
            "next-2",
        ]
        rows = SessionManager(tmp_path).get_or_create("role:mira").messages
        assert [
            row["content"]
            for row in rows
            if row["role"] == "user"
            and row["content"] in ("alice-first", "bob-request", "alice-supplement")
        ] == ["alice-first", "bob-request", "alice-supplement"]


async def test_flag_off_keeps_ordinary_serial_chat_behavior(tmp_path, monkeypatch):
    async with natural_dispatcher(
        tmp_path, monkeypatch, stage="generation", enabled=False
    ) as env:
        await env.receive("first")
        await asyncio.wait_for(env.started.wait(), 3)
        await env.receive("second")
        await until(lambda: env.bus.inbound_size == 0)
        env.release.set()
        await until(lambda: env.candidate.references == 0)
        await env.bus.drain_outbound()
        assert len(env.requests) == 2
        assert [m.content for m in env.sent] == [
            "prefix\n<message-break/>\ntail",
            "next-1",
        ]


async def test_supplement_finishes_only_started_tool_and_next_turn_sees_its_fact(
    tmp_path, monkeypatch
):
    async with natural_dispatcher(tmp_path, monkeypatch, stage="tool") as env:
        await env.receive("first")
        await asyncio.wait_for(env.started.wait(), 3)
        await env.receive("second")
        await until(lambda: env.bus.inbound_size == 0)
        assert len(env.requests) == 1
        assert env.tool_calls == ["executed"]
        env.release.set()
        await until(lambda: env.candidate.references == 0)
        assert env.tool_calls == ["executed"]
        assert len(env.requests) == 2
        history = env.requests[1]["messages"]
        assert any(
            m.get("role") == "tool" and "durable tool fact" in str(m.get("content"))
            for m in history
        )
        assert not any(
            "private tool preamble" in str(m.get("content")) for m in history
        )
        assert [m.content for m in env.sent] == ["next-1"]
        rows = SessionManager(tmp_path).get_or_create("role:mira").messages
        calls = [
            call
            for row in rows
            for group in row.get("tool_chain") or []
            for call in group.get("calls") or []
        ]
        assert [call["call_id"] for call in calls] == ["first-tool"]


@pytest.mark.parametrize("lifecycle", ["disable", "delete", "generation"])
async def test_lifecycle_discards_tail_and_cleans_registration(
    tmp_path, monkeypatch, lifecycle
):
    async with natural_dispatcher(tmp_path, monkeypatch) as env:
        await env.receive("first")
        await asyncio.wait_for(env.started.wait(), 3)
        if lifecycle == "disable":
            env.host.roles.update_role(
                "mira", runtime_config={"natural_chat_enabled": False}
            )
        elif lifecycle == "delete":
            env.host.roles.delete_role("mira")
        else:
            env.candidate.reply_sequences.stop()
        env.release.set()
        await until(lambda: env.candidate.references == 0)
        assert [m.content for m in env.sent] == ["prefix"]
        assert not env.candidate.reply_sequences._replies
        assert not env.candidate.reply_sequences._plans


async def test_background_result_runs_on_new_loop_and_releases_short_lease(
    tmp_path, monkeypatch
):
    monkeypatch.setattr("bootstrap.tools._resolve_plugin_dirs", lambda _: [])
    config = Config(
        provider="",
        model="",
        api_key="",
        model_registrations=[],
        memory_optimizer_enabled=False,
    )
    app = AppRuntime(
        config,
        tmp_path,
        features=RuntimeFeatures(enable_message_channels=False, enable_proactive=False),
    )
    await app.start()
    old_loop = app.core.loop
    old_runner = AsyncMock()
    monkeypatch.setattr(old_loop, "process_background_result", old_runner)
    saved_runner = app._dispatcher.process_background_result
    candidate = await app.prepare(replace(config, max_tokens=2048))
    current_runner = AsyncMock()
    monkeypatch.setattr(
        candidate.core.loop, "process_background_result", current_runner
    )
    await app.publish(candidate)
    try:
        context, admission = object(), lambda: None
        await saved_runner(context, admission)
        current_runner.assert_awaited_once_with(context, admission)
        old_runner.assert_not_called()
        assert candidate.references == 0
    finally:
        await app.shutdown()


async def test_chat_lanes_preserve_order_and_release_accepted_leases_on_shutdown():
    bus = MessageBus()
    entered, other_done, release = (asyncio.Event() for _ in range(3))
    seen = []

    async def process(item):
        seen.append(item.content)
        if item.content == "a1":
            entered.set()
            await release.wait()
        if item.content == "b1":
            other_done.set()

    candidate = RuntimeCandidate(
        1,
        SimpleNamespace(loop=SimpleNamespace(process_inbound=process)),
        SimpleNamespace(),
    )
    app = SimpleNamespace(
        bus=bus, wait_for_admission=AsyncMock(), acquire=candidate.acquire
    )
    bus.bind_runtime_admission(candidate.acquire)
    for chat, content in (("a", "a1"), ("a", "a2"), ("b", "b1")):
        await bus.publish_inbound(
            InboundMessage(
                "qqbot",
                "user",
                chat,
                content,
                metadata={"session_key_override": "role:mira"},
            )
        )
    task = asyncio.create_task(RuntimeDispatcher(app).run())
    await asyncio.wait_for(entered.wait(), 1)
    await asyncio.wait_for(other_done.wait(), 1)
    assert seen == ["a1", "b1"]
    assert candidate.references == 2
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert candidate.references == 0
    assert seen == ["a1", "b1"]


@pytest.mark.parametrize(
    "channel,chat_id", [("desktop", "role:mira"), ("telegram", "42")]
)
async def test_spawn_completion_keeps_internal_tracking_and_dispatcher_alive(
    tmp_path, channel, chat_id
):
    from unittest.mock import Mock
    from agent.background.subagent_manager import SubagentManager
    from agent.looping.core import AgentLoop
    from agent.looping.interrupt import current_tracking_key
    from agent.turns.reply_interruption import current_reply_interruption
    from bus.event_bus import EventBus
    from bus.events import SpawnCompletionItem
    from core.common.runtime_scope import bind_runtime
    from shiori_sdk.messages import OutboundMessage

    bus = MessageBus()
    loop = object.__new__(AgentLoop)
    loop.bus = bus
    loop._event_bus = EventBus()
    loop._processing_state = None
    loop._active_tasks = {}
    loop._active_turn_states = {}
    loop._interrupt_states = {}
    entered, release, following = (asyncio.Event() for _ in range(3))
    seen = []

    async def process(item, key, *, dispatch_outbound):
        seen.append(
            (item, key, current_tracking_key(key), current_reply_interruption())
        )
        if isinstance(item, SpawnCompletionItem):
            loop._append_partial_thinking(key, "internal progress")
            entered.set()
            await release.wait()
        else:
            following.set()
        return OutboundMessage(item.channel, item.chat_id, "handled")

    loop._core_runner = SimpleNamespace(process=process)
    candidate = RuntimeCandidate(1, SimpleNamespace(loop=loop), SimpleNamespace())
    bus.bind_runtime_admission(candidate.acquire)
    bus.subscribe_outbound(channel, AsyncMock(), supports_reply_sequence=True)
    app = SimpleNamespace(
        bus=bus, wait_for_admission=AsyncMock(), acquire=candidate.acquire
    )
    producer = SubagentManager(
        provider=Mock(),
        workspace=tmp_path,
        bus=bus,
        model="test",
        max_tokens=256,
        fetch_requester=object(),
    )
    existing_input = InboundMessage(
        channel,
        "alice",
        chat_id,
        "ordinary request",
        metadata={
            "role_id": "mira",
            "account_id": "fixture",
            "chat_type": "private",
        },
    )
    existing_reply = candidate.reply_sequences.admit(existing_input)
    dispatcher = asyncio.create_task(RuntimeDispatcher(app).run())
    try:
        async with candidate.acquire() as lease:
            with bind_runtime(lease):
                await producer._announce_result(
                    job_id="job",
                    label="report",
                    task="original task",
                    origin_channel=channel,
                    origin_chat_id=chat_id,
                    status="completed",
                    exit_reason="completed",
                    result="completed fact",
                    decision=None,
                )
        await until(lambda: entered.is_set() or dispatcher.done())
        if dispatcher.done():
            await dispatcher
        [(item, key, tracking, interruption)] = seen
        assert isinstance(item, SpawnCompletionItem)
        assert item.event.result == "completed fact"
        assert key == item.session_key == f"{channel}:{chat_id}"
        assert tracking == key
        assert interruption is None
        assert loop._active_turn_states[key].partial_thinking == "internal progress"
        assert (
            loop._active_turn_states[key].original_user_message
            == "[后台任务完成] report"
        )
        assert key in loop._active_tasks
        assert not existing_reply.invalidated
        assert candidate.reply_sequences._plans == {existing_reply}
        assert candidate.references == 1

        # A typed completion must not terminate the global consumer or block a
        # different chat while its own processing is still pending.
        await bus.publish_inbound(
            InboundMessage("telegram", "bob", "other", "following")
        )
        await asyncio.wait_for(following.wait(), 2)
        release.set()
        await until(lambda: candidate.references == 0)
        assert not dispatcher.done()
        assert loop._active_tasks == {}
        assert loop._active_turn_states == {}
        assert not existing_reply.invalidated
        assert len(seen) == 2
    finally:
        release.set()
        dispatcher.cancel()
        await asyncio.gather(dispatcher, return_exceptions=True)
        candidate.reply_sequences.forget(existing_input, existing_reply)
        await loop._event_bus.aclose()
