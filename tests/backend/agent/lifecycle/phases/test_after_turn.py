"""Explicit account delivery suppresses the implicit source transport send."""

from __future__ import annotations


from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest

from agent.lifecycle.phases.after_turn import (
    _apply_turn_affection,
    _dispatch,
    _memory_extra,
    _turn_committed,
    _turn_finished,
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
from core.roles import RoleStore
from core.roles.affection_host import HostAffectionSources
from plugins.affection.backend.relationship import RoleRelationshipRuntimeService
from core.roles.reply_state import AffectionChange
from session.manager import SessionManager
from agent.turns.outbound import BusOutboundPort
from bus.event_bus import EventBus
from bus.queue import MessageBus
from tests.support.generation_getters import turn_getters


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
    snap = SimpleNamespace(
        state=state,
        ctx=SimpleNamespace(
            reply="",
            tools_used=[],
            tool_chain=[],
            thinking=None,
            response_metadata=SimpleNamespace(raw_text=""),
            meme_tag=None,
            media=[],
            outbound_metadata={},
        ),
    )
    committed = _turn_committed(cast(Any, snap), budget={}, react_stats={})
    assert committed.external_message_id == "bot-input"
    assert committed.assistant_response == ""


@pytest.mark.asyncio
async def test_account_send_suppresses_default_dispatch() -> None:
    port = SimpleNamespace(dispatch=AsyncMock())
    outbound = OutboundMessage(
        channel="qq",
        chat_id="42",
        content="reply",
        metadata={"account_delivery_sent": True},
    )
    snap = SimpleNamespace(
        state=SimpleNamespace(dispatch_outbound=True), outbound=outbound
    )
    await _dispatch(cast(Any, port), cast(Any, snap))
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
    snap = cast(
        Any,
        SimpleNamespace(
            state=state,
            outbound=outbound,
            ctx=SimpleNamespace(
                reply=outbound.content,
                tools_used=[],
                tool_chain=[],
                thinking=None,
                response_metadata=SimpleNamespace(raw_text=outbound.content),
                meme_tag=None,
                media=[],
                outbound_metadata={},
            ),
        ),
    )
    bus, events = MessageBus(), EventBus()
    observed = []

    def observe(_committed: TurnCommitted) -> None:
        observed.append(
            (
                bus.has_pending_outbound(message.channel, message.chat_id, "bot-input"),
                bus.outbound_size,
            )
        )

    events.on(TurnCommitted, observe)
    await events.fanout(_turn_committed(snap, budget={}, react_stats={}))
    assert observed == [(False, 0)]
    assert _turn_finished(snap).will_dispatch is expected
    await _dispatch(BusOutboundPort(bus), snap)
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
    snap = SimpleNamespace(
        state=SimpleNamespace(dispatch_outbound=True), outbound=outbound
    )
    await _dispatch(cast(Any, port), cast(Any, snap))

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
async def test_committed_affection_change_is_recorded(
    tmp_path,
) -> None:
    manager = SessionManager(tmp_path)
    session = manager.get_or_create("role:yin")
    session.metadata["role_id"] = "yin"
    relationship = RoleRelationshipRuntimeService(
        HostAffectionSources(
            workspace=tmp_path,
            role_store=RoleStore(tmp_path),
            session_manager=manager,
            presence=manager.presence,
        )
    )
    relationship.affection.initialize("yin", value=50, reason="初识")
    state = SimpleNamespace(
        session=session,
        affection_change=AffectionChange(3, "他一直记得我说过的话。"),
    )

    with turn_getters(affection=relationship):
        await _apply_turn_affection(cast(Any, state))

    history = relationship.affection.read_history("yin")
    assert [(e.delta, e.reason, e.source) for e in history[1:]] == [
        (3, "他一直记得我说过的话。", "turn")
    ]
