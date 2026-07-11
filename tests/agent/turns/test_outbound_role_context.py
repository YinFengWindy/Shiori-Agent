from __future__ import annotations

import pytest

from agent.turns.outbound import OutboundDispatch, PushToolOutboundPort


@pytest.mark.asyncio
async def test_push_outbound_port_passes_role_context() -> None:
    calls: list[dict[str, object]] = []

    class PushTool:
        async def execute(self, **kwargs):
            calls.append(kwargs)
            return "文本已发送"

    port = PushToolOutboundPort(PushTool(), execution_context={"role_id": "mira"})
    sent = await port.dispatch(
        OutboundDispatch(channel="telegram", chat_id="123", content="hello")
    )

    assert sent is True
    assert calls[0]["role_id"] == "mira"
