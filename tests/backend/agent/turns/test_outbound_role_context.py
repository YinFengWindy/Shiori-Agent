from __future__ import annotations

import pytest

from agent.tools.message_push import PushOutcome
from agent.turns.outbound import (
    DeliveryReceipt,
    OutboundDispatch,
    OutboundDispatchError,
    PushToolOutboundPort,
)


@pytest.mark.asyncio
async def test_push_outbound_port_passes_role_context() -> None:
    calls: list[dict[str, object]] = []

    class PushTool:
        async def push(self, **kwargs):
            calls.append(kwargs)
            return PushOutcome("文本已发送")

    port = PushToolOutboundPort(PushTool(), execution_context={"role_id": "mira"})
    sent = await port.dispatch(
        OutboundDispatch(channel="telegram", chat_id="123", content="hello")
    )

    assert sent == DeliveryReceipt()
    assert calls[0]["role_id"] == "mira"


@pytest.mark.asyncio
async def test_push_outbound_port_removes_internal_citation_markers() -> None:
    calls: list[dict[str, object]] = []

    class PushTool:
        async def push(self, **kwargs):
            calls.append(kwargs)
            return PushOutcome("文本已发送")

    port = PushToolOutboundPort(PushTool(), execution_context={"role_id": "mira"})
    sent = await port.dispatch(
        OutboundDispatch(
            channel="telegram",
            chat_id="123",
            content="我记得这件事 §cited:[mem-1,mem-2]§",
        )
    )

    assert sent == DeliveryReceipt()
    assert calls[0]["message"] == "我记得这件事"


@pytest.mark.asyncio
async def test_push_outbound_port_keeps_explicit_permission_rejection_as_false() -> (
    None
):
    class PushTool:
        async def push(self, **kwargs):
            raise PermissionError("role is not bound")

    port = PushToolOutboundPort(PushTool())

    sent = await port.dispatch(
        OutboundDispatch(channel="telegram", chat_id="123", content="hello")
    )

    assert sent is None


@pytest.mark.asyncio
async def test_push_outbound_port_surfaces_transport_failure() -> None:
    class PushTool:
        async def push(self, **kwargs):
            raise ConnectionError("network unavailable")

    port = PushToolOutboundPort(PushTool())

    with pytest.raises(OutboundDispatchError) as exc_info:
        await port.dispatch(
            OutboundDispatch(channel="telegram", chat_id="123", content="hello")
        )

    assert exc_info.value.channel == "telegram"
    assert exc_info.value.chat_id == "123"
    assert "network unavailable" in str(exc_info.value)


@pytest.mark.asyncio
async def test_push_outbound_port_surfaces_unregistered_channel_result() -> None:
    class PushTool:
        async def push(self, **kwargs):
            return PushOutcome("渠道 'telegram' 未注册，可用渠道：['（无）']")

    port = PushToolOutboundPort(PushTool())

    with pytest.raises(OutboundDispatchError, match="未注册"):
        await port.dispatch(
            OutboundDispatch(channel="telegram", chat_id="123", content="hello")
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "result", ["发送失败：image failed", "文本已发送；渠道不支持发送图片"]
)
async def test_partial_media_failure_cannot_be_hidden_by_later_image_success(result):
    calls = []

    class PushTool:
        async def push(self, **kwargs):
            calls.append(kwargs)
            return PushOutcome(result if len(calls) == 1 else "图片已发送")

    port = PushToolOutboundPort(PushTool())
    with pytest.raises(OutboundDispatchError):
        await port.dispatch(
            OutboundDispatch(
                channel="telegram",
                chat_id="123",
                content="hello",
                media=["one.png", "two.png"],
            )
        )
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_push_outbound_port_receipt_keeps_first_reported_message_id():
    ids = iter([(), ("image-2",)])

    class PushTool:
        async def push(self, **kwargs):
            return PushOutcome("文本已发送；图片已发送", next(ids))

    port = PushToolOutboundPort(PushTool())
    receipt = await port.dispatch(
        OutboundDispatch(
            channel="qqbot",
            chat_id="c2c:user-1",
            content="hello",
            media=["one.png", "two.png"],
        )
    )

    assert receipt == DeliveryReceipt(external_message_id="image-2")
