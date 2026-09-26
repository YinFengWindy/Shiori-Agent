"""Explicit account delivery suppresses the implicit source transport send."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from agent.lifecycle.phases.after_turn import AfterTurnFrame, _DispatchOutboundModule
from agent.account_delivery import AccountDelivery
from agent.account_delivery.turn_state import account_delivery_scope
from bus.events import OutboundMessage
from core.accounts import AccountRegistry
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
    accounts = AccountRegistry(tmp_path, lambda role_id: role_id == "mira")
    accounts.set_plugin_enabled("chat", True)
    account = accounts.register(
        plugin_id="chat",
        platform="chat",
        platform_account_id="bot",
        config_ref="bot",
        token="live",
    )
    accounts.assign(account.record.id, "mira")
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
                account.record.id, "mira", "private", "remote-user", "hi", None
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
