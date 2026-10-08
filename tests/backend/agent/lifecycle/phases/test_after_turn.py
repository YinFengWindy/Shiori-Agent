"""Explicit account delivery suppresses the implicit source transport send."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from agent.lifecycle.phases.after_turn import (
    AfterTurnFrame,
    _ApplyTurnAffectionModule,
    _DispatchOutboundModule,
    _memory_extra,
)
from agent.lifecycle.types import TurnState
from agent.account_delivery import AccountDelivery
from agent.account_delivery.turn_state import account_delivery_scope
from shiori_sdk.messages import InboundMessage, OutboundMessage
from conversation.context_scope import turn_context_view
from shiori_sdk.channels.threads import network_thread_id
from core.accounts import AccountRegistry
from shiori_sdk.accounts.targets import AccountTarget
from core.accounts.delivery_ledger import AccountDeliveryLedger
from core.identity import UserIdentityStore
from core.roles import RoleRelationshipRuntimeService, RoleStore
from core.roles.reply_state import AffectionChange
from proactive_v2.presence import PresenceStore
from session.manager import SessionManager


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
