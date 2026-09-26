"""Explicit account delivery suppresses the implicit source transport send."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from agent.lifecycle.phases.after_turn import AfterTurnFrame, _DispatchOutboundModule
from bus.events import OutboundMessage


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
