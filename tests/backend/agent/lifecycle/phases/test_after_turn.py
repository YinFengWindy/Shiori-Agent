"""Explicit account delivery suppresses the implicit source transport send."""

from __future__ import annotations

import asyncio
import json
from uuid import uuid4

import httpx

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from agent.lifecycle.phases.after_turn import (
    AfterTurnFrame,
    AfterTurnPhase,
    _ApplyTurnAffectionModule,
    _DispatchOutboundModule,
    _memory_extra,
    _BuildTurnCommittedModule,
    _BuildAfterTurnCtxModule,
    _FanoutTurnCommittedModule,
)
from agent.lifecycle.types import TurnState
from agent.account_delivery import AccountDelivery
from agent.account_delivery.turn_state import account_delivery_scope
from shiori_sdk.messages import InboundMessage, OutboundMessage
from conversation.context_scope import turn_context_view
from shiori_sdk.channels.threads import network_thread_id
from core.accounts import AccountRegistry
from shiori_sdk.accounts.targets import AccountTarget
from shiori_sdk.memory.committed import TurnCommitted
from core.accounts.delivery_ledger import AccountDeliveryLedger
from core.identity import UserIdentityStore
from core.roles import RoleRelationshipRuntimeService, RoleStore
from core.roles.reply_state import AffectionChange
from proactive_v2.presence import PresenceStore
from session.manager import SessionManager
from agent.turns.outbound import BusOutboundPort
from bus.event_bus import EventBus
from bus.queue import MessageBus


@pytest.mark.asyncio
async def test_silent_committed_turn_keeps_its_original_inbound_message_id(tmp_path):
    session = SessionManager(tmp_path).get_or_create("role:mira")
    session.metadata["role_id"] = "mira"
    state = TurnState(
        msg=InboundMessage(
            channel="grok_bot_a",
            sender="peer",
            chat_id="dm:peer",
            content="不用回复",
            metadata={
                "external_message_id": "bot-input",
                "thread_id": "network-thread",
            },
        ),
        session_key=session.key,
        dispatch_outbound=False,
        session=session,
    )
    frame = AfterTurnFrame(
        input=SimpleNamespace(
            state=state,
            ctx=SimpleNamespace(
                reply="",
                tools_used=[],
                thinking=None,
                response_metadata=SimpleNamespace(raw_text=""),
                meme_tag=None,
                media=[],
                outbound_metadata={},
            ),
        )
    )
    frame.slots.update(
        {
            "turn:tool_chain": [],
            "turn:omit_user_turn": False,
            "turn:budget": {},
            "turn:react_stats": {},
            "turn:extra": {},
        }
    )
    await _BuildTurnCommittedModule().run(frame)
    committed = frame.slots["turn:committed"]
    assert isinstance(committed, TurnCommitted)
    assert committed.external_message_id == "bot-input"
    assert committed.assistant_response == ""


@pytest.mark.asyncio
async def test_account_send_suppresses_default_dispatch() -> None:
    port = SimpleNamespace(dispatch=AsyncMock())
    module = _DispatchOutboundModule(port)
    outbound = OutboundMessage(
        channel="qq",
        chat_id="42",
        content="reply",
        metadata={"account_delivery_sent": True},
    )
    frame = AfterTurnFrame(
        input=SimpleNamespace(
            state=SimpleNamespace(dispatch_outbound=True), outbound=outbound
        )
    )
    await module.run(frame)
    port.dispatch.assert_not_awaited()


@pytest.mark.parametrize(
    "dispatch_outbound, account_sent, expected",
    [(True, False, True), (True, True, False), (False, False, False)],
)
async def test_commit_observers_receive_actual_dispatch_intent_before_enqueue(
    tmp_path, dispatch_outbound, account_sent, expected
):
    session = SessionManager(tmp_path).get_or_create("role:mira")
    session.metadata["role_id"] = "mira"
    message = InboundMessage(
        channel="grok_bot_a",
        sender="peer",
        chat_id="dm:peer",
        content="hello",
        metadata={"external_message_id": "bot-input"},
    )
    state = TurnState(
        msg=message,
        session_key=session.key,
        session=session,
        dispatch_outbound=dispatch_outbound,
    )
    outbound = OutboundMessage(
        channel=message.channel,
        chat_id=message.chat_id,
        content="nonempty reply",
        metadata={
            "external_message_id": "bot-input",
            "account_delivery_sent": account_sent,
        },
    )
    frame = AfterTurnFrame(
        input=SimpleNamespace(
            state=state,
            outbound=outbound,
            ctx=SimpleNamespace(
                reply=outbound.content,
                tools_used=[],
                thinking=None,
                response_metadata=SimpleNamespace(raw_text=outbound.content),
                meme_tag=None,
                media=[],
                outbound_metadata={},
            ),
        )
    )
    frame.slots.update(
        {
            "turn:tool_chain": [],
            "turn:omit_user_turn": False,
            "turn:budget": {},
            "turn:react_stats": {},
            "turn:extra": {},
        }
    )
    bus, events = MessageBus(), EventBus()
    observed = []

    def observe(committed: TurnCommitted) -> None:
        observed.append(
            (
                committed.will_dispatch,
                bus.has_pending_outbound(message.channel, message.chat_id, "bot-input"),
                bus.outbound_size,
            )
        )

    events.on(TurnCommitted, observe)
    slots = dict(frame.slots)
    port = BusOutboundPort(bus)

    class Stages:
        async def run(self, current: AfterTurnFrame) -> AfterTurnFrame:
            current.slots.update(slots)
            await _BuildTurnCommittedModule().run(current)
            await _FanoutTurnCommittedModule(events).run(current)
            await _BuildAfterTurnCtxModule().run(current)
            assert current.slots["turn:ctx"].will_dispatch is expected
            await _DispatchOutboundModule(port).run(current)
            current.output = current.input.outbound
            return current

    await AfterTurnPhase([Stages()], port).run(frame.input)
    assert observed == [(expected, expected, 0)]
    assert (
        bus.has_pending_outbound(message.channel, message.chat_id, "bot-input")
        is expected
    )


@pytest.mark.asyncio
async def test_uncertain_account_send_does_not_auto_dispatch_original(tmp_path) -> None:
    accounts = AccountRegistry(lambda role_id: role_id == "mira")
    account = accounts.register(
        plugin_id="chat",
        platform="chat",
        platform_account_id="bot",
        config_ref="bot",
        token="live",
        role_id="mira",
    )
    accounts.report(account.record.id, "live", connection="online")

    async def timed_out(payload):
        raise TimeoutError("platform reply lost")

    rpc = SimpleNamespace(resolve=lambda name: ("chat", timed_out))
    ledger = AccountDeliveryLedger(tmp_path)
    delivery = AccountDelivery(accounts, rpc, ledger, UserIdentityStore(tmp_path))
    state: dict[str, bool] = {}
    with account_delivery_scope(state):
        with pytest.raises(TimeoutError):
            await delivery.send(
                "chat", "mira", AccountTarget("private", "remote-user"), "hi"
            )

    port = SimpleNamespace(dispatch=AsyncMock())
    outbound = OutboundMessage(
        channel="desktop",
        chat_id="role:mira",
        content="hi",
        metadata={"account_delivery_sent": state.get("sent", False)},
    )
    frame = AfterTurnFrame(
        input=SimpleNamespace(
            state=SimpleNamespace(dispatch_outbound=True), outbound=outbound
        )
    )
    await _DispatchOutboundModule(port).run(frame)

    [attempt] = AccountDeliveryLedger(tmp_path).list_for_role("mira")
    assert attempt.status == "pending"
    port.dispatch.assert_not_awaited()


@pytest.mark.parametrize("sender_is_user", [False, True])
def test_only_the_users_own_group_turn_is_offered_to_memory_extraction(
    tmp_path, sender_is_user
) -> None:
    group = network_thread_id("mira", "qq", "g1")
    state = TurnState(
        msg=InboundMessage(
            channel="qq",
            sender="902" if sender_is_user else "555",
            chat_id="g1",
            content="我最喜欢狗了",
            metadata={"chat_type": "group", "thread_id": group}
            | ({"sender_is_user": True} if sender_is_user else {}),
        ),
        session_key="role:mira",
        dispatch_outbound=False,
        context_view=turn_context_view(tmp_path, "mira", group),
    )

    extra = _memory_extra(state)

    if sender_is_user:
        assert extra == {}
    else:
        assert extra == {"skip_post_memory": True, "not_user_authored": True}


@pytest.mark.asyncio
async def test_committed_affection_change_is_recorded_and_saved_with_the_session(
    tmp_path,
) -> None:
    manager = SessionManager(tmp_path)
    session = manager.get_or_create("role:yin")
    session.metadata["role_id"] = "yin"
    relationship = RoleRelationshipRuntimeService(
        tmp_path,
        role_store=RoleStore(tmp_path),
        session_manager=manager,
        presence=PresenceStore(manager._store),
    )
    relationship.affection.initialize("yin", value=50, reason="初识")
    frame = AfterTurnFrame(
        input=SimpleNamespace(
            state=SimpleNamespace(
                session=session,
                affection_change=AffectionChange(3, "他一直记得我说过的话。"),
            )
        )
    )

    await _ApplyTurnAffectionModule(relationship).run(frame)

    history = relationship.affection.read_history("yin")
    assert [(e.delta, e.reason, e.source) for e in history[1:]] == [
        (3, "他一直记得我说过的话。", "turn")
    ]
    # The saved session carries the new summary the sidebar shows.
    reloaded = SessionManager(tmp_path).get_or_create("role:yin")
    assert reloaded.metadata["affection"]["value"] == 53


@pytest.mark.parametrize("outcome", ["failure", "cancel"])
async def test_after_turn_preparation_releases_on_failure_or_cancellation(outcome):
    bus = MessageBus()
    entered, release = asyncio.Event(), asyncio.Event()
    message = OutboundMessage(
        "chat", "peer", "reply", metadata={"external_message_id": "parent"}
    )

    class BlockedStage:
        async def run(self, frame: AfterTurnFrame) -> AfterTurnFrame:
            entered.set()
            await release.wait()
            raise RuntimeError("observer failed")

    snapshot = SimpleNamespace(
        state=SimpleNamespace(dispatch_outbound=True), outbound=message
    )
    task = asyncio.create_task(
        AfterTurnPhase([BlockedStage()], BusOutboundPort(bus)).run(snapshot)
    )
    try:
        await asyncio.wait_for(entered.wait(), 2)
        assert bus.has_pending_outbound("chat", "peer", "parent")
        assert bus.outbound_size == 0
        if outcome == "cancel":
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        else:
            release.set()
            with pytest.raises(RuntimeError, match="observer failed"):
                await task
        assert not bus.has_pending_outbound("chat", "peer", "parent")
        assert bus.outbound_size == 0
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


async def test_reconnect_before_enqueue_preserves_grok_parent_until_real_delivery(
    tmp_path, monkeypatch
):
    from plugins.grok_bot.backend.config import ConnectionConfig
    from plugins.grok_bot.backend.connection import GrokConnection
    from plugins.grok_bot.backend.protocol import BotMessage
    from shiori_sdk.testing.channel_context import fake_channel_context
    from shiori_sdk.testing.channel_hub import FakeChannelHub
    from shiori_sdk.testing.storage import FakeKV
    from shiori_sdk.testing.events import FakeEvents

    bus, events, hub, kv = MessageBus(), FakeEvents(), FakeChannelHub(), FakeKV()
    config = ConnectionConfig(
        connection_id=uuid4().hex,
        peer_id=uuid4().hex,
        role_id="mira",
        webhook_url="https://example.test/hook",
        webhook_key="test-key",
        callback_token="x" * 32,
    )
    sent = []

    def post(request):
        sent.append(json.loads(request.content))
        return httpx.Response(200)

    def make_connection():
        return GrokConnection(
            config,
            kv,
            tmp_path / "data",
            tmp_path / "client.ps1",
            config_changed=lambda value: None,
            status_changed=lambda state, error: None,
            transport=httpx.MockTransport(post),
        )

    context = fake_channel_context(tmp_path, bus=bus, event_bus=events, channel_hub=hub)
    connection = make_connection()
    await connection.start(context)
    await connection.receive("messages", {"message_id": "parent", "text": "hello"})
    observed, resume = asyncio.Event(), asyncio.Event()
    message = OutboundMessage(
        connection.name,
        config.chat_id,
        "queued reply",
        metadata={"external_message_id": "parent"},
        committed_message_id="reply",
    )
    port = BusOutboundPort(bus)

    class PausedAfterCommit:
        async def run(self, frame: AfterTurnFrame) -> AfterTurnFrame:
            await events.fanout(
                TurnCommitted(
                    session_key="role:mira",
                    channel=message.channel,
                    chat_id=message.chat_id,
                    input_message="hello",
                    persisted_user_message="hello",
                    assistant_response="queued reply",
                    tools_used=[],
                    external_message_id="parent",
                    will_dispatch=True,
                )
            )
            observed.set()
            await resume.wait()
            await _DispatchOutboundModule(port).run(frame)
            frame.output = message
            return frame

    snapshot = SimpleNamespace(
        state=SimpleNamespace(dispatch_outbound=True), outbound=message
    )
    phase = asyncio.create_task(
        AfterTurnPhase([PausedAfterCommit()], port).run(snapshot)
    )
    dispatcher = None
    try:
        await asyncio.wait_for(observed.wait(), 2)
        assert bus.outbound_size == 0
        assert bus.has_pending_outbound(connection.name, config.chat_id, "parent")
        await connection.stop()
        connection = make_connection()
        await connection.start(context)
        assert connection._recovery is not None
        await connection._recovery
        assert [item.message_id for item in connection.journal.pending()] == ["parent"]
        monkeypatch.setattr("plugins.grok_bot.backend.exchange.MAX_RECORDS", 4)
        for index in range(4):
            await connection.send(BotMessage(f"other-{index}", "new topic"))
        assert "parent" in connection.journal.state.messages
        resume.set()
        await phase
        assert bus.has_pending_outbound(connection.name, config.chat_id, "parent")
        dispatcher = asyncio.create_task(bus.dispatch_outbound())
        await asyncio.wait_for(bus._outbound.join(), 2)
        assert sent[-1]["text"] == "queued reply"
        assert sent[-1]["reply_to"] == "parent"
        assert hub.deliveries[-1]["delivery_status"] == "sent"
        assert connection.journal.pending() == []
        assert not bus.has_pending_outbound(connection.name, config.chat_id, "parent")
    finally:
        phase.cancel()
        await asyncio.gather(phase, return_exceptions=True)
        bus.stop()
        if dispatcher is not None:
            dispatcher.cancel()
            await asyncio.gather(dispatcher, return_exceptions=True)
        await connection.stop()
