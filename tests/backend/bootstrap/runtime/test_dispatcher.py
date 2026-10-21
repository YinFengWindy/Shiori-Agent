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
from tests.support.host_external_turns import ExternalTurnHost
from tests.support.chat_replies import chat_reply
from session.manager import SessionManager


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
async def test_admitted_supplements_stop_only_unsent_reply_and_keep_all_input(
    tmp_path, monkeypatch, stage
):
    async with natural_dispatcher(tmp_path, monkeypatch, stage=stage) as env:
        await env.receive("first", chat_type="group")
        await asyncio.wait_for(env.started.wait(), 3)
        await env.receive("second", chat_type="group")
        await env.receive("third", chat_type="group")
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


@pytest.mark.parametrize("change", ["sender", "chat", "sidechat"])
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
