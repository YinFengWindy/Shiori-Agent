"""Explicit account delivery suppresses the implicit source transport send."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from agent.lifecycle.phases.after_turn import (
    AfterTurnFrame,
    _DispatchOutboundModule,
    _memory_extra,
)
from agent.lifecycle.types import TurnState
from agent.account_delivery import AccountDelivery
from agent.account_delivery.turn_state import account_delivery_scope
from bus.events import InboundMessage, OutboundMessage
from conversation.context_scope import turn_context_view
from conversation.service import network_thread_id
from core.accounts import AccountRegistry
from core.accounts.target_contract import AccountTarget
from core.accounts.delivery_ledger import AccountDeliveryLedger


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
    delivery = AccountDelivery(accounts, rpc, ledger)
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
