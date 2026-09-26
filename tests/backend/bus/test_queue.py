import asyncio
from contextlib import suppress
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from bus.events import InboundMessage, OutboundMessage, SpawnCompletionItem
from bus.errors import NonRetryableDeliveryError
from bus.queue import MessageBus
from bootstrap.runtime.generations import RuntimeCandidate


@pytest.mark.asyncio
async def test_subscription_is_idempotent_and_can_be_removed():
    bus = MessageBus()
    received = []

    async def receive(message):
        received.append(message.content)

    bus.subscribe_outbound("chat", receive)
    bus.subscribe_outbound("chat", receive)
    await bus._dispatch_message(
        OutboundMessage(channel="chat", chat_id="one", content="hello")
    )
    assert received == ["hello"]
    bus.unsubscribe_outbound("chat", receive)
    await bus._dispatch_message(
        OutboundMessage(channel="chat", chat_id="one", content="removed")
    )
    assert received == ["hello"]


@pytest.mark.asyncio
async def test_buffered_message_uses_replacement_transport_after_handover():
    bus = MessageBus()
    received = []
    delivered = asyncio.Event()

    async def old(message):
        received.append("old")

    async def new(message):
        received.append(message.content)
        delivered.set()

    bus.subscribe_outbound("chat", old)
    async with bus.transport_lock:
        dispatcher = asyncio.create_task(bus.dispatch_outbound())
        await bus.publish_outbound(
            OutboundMessage(channel="chat", chat_id="one", content="buffered")
        )
        await asyncio.sleep(0)
        assert received == []
        bus.unsubscribe_outbound("chat", old)
        bus.subscribe_outbound("chat", new)
    try:
        await asyncio.wait_for(delivered.wait(), 1)
        assert received == ["buffered"]
    finally:
        bus.stop()
        dispatcher.cancel()
        with suppress(asyncio.CancelledError):
            await dispatcher


@pytest.mark.asyncio
async def test_late_completion_after_intake_closes_releases_its_generation():
    bus = MessageBus()
    await bus.close_inbound()
    core = SimpleNamespace(
        stop=AsyncMock(), memory_runtime=SimpleNamespace(aclose=AsyncMock())
    )
    generation = RuntimeCandidate(1, core, SimpleNamespace())
    retained = generation.acquire()
    await generation.retire()
    await bus.publish_inbound(
        SpawnCompletionItem("desktop", "one", object(), runtime_lease=retained)
    )
    assert generation.drained.is_set()
    assert bus.inbound_size == 0


@pytest.mark.asyncio
async def test_message_bus_retries_failed_outbound_dispatch():
    bus = MessageBus()
    await bus.publish_inbound(InboundMessage("telegram", "u", "1", "hello"))
    inbound = await bus.consume_inbound()
    assert inbound.session_key == "telegram:1"

    sent: list[str] = []
    attempts = {"count": 0}

    async def callback(msg: OutboundMessage) -> None:
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise RuntimeError("first")
        sent.append(msg.content)

    bus.subscribe_outbound("telegram", callback)
    task = asyncio.create_task(bus.dispatch_outbound())
    await bus.publish_outbound(OutboundMessage("telegram", "1", "payload"))
    for _ in range(300):
        if sent:
            break
        await asyncio.sleep(0.01)
    bus.stop()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert sent == ["payload"]
    assert bus.inbound_size == 0
    assert bus.outbound_size == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("fail_on_retry", [False, True])
async def test_nonretryable_delivery_never_replays_or_sends_error_notice(
    monkeypatch, fail_on_retry
):
    sleep = AsyncMock()
    monkeypatch.setattr("bus.queue.asyncio.sleep", sleep)
    bus = MessageBus()
    callback = AsyncMock(
        side_effect=(
            [RuntimeError("retryable"), NonRetryableDeliveryError("uncertain write")]
            if fail_on_retry
            else NonRetryableDeliveryError("uncertain write")
        )
    )
    bus.subscribe_outbound("chat", callback)
    message = OutboundMessage("chat", "one", "payload")
    await bus._dispatch_message(message)
    assert callback.await_count == (2 if fail_on_retry else 1)
    assert all(call.args == (message,) for call in callback.await_args_list)
    assert sleep.await_count == (1 if fail_on_retry else 0)


@pytest.mark.asyncio
async def test_retryable_delivery_still_sends_error_notice_after_second_failure(
    monkeypatch,
):
    monkeypatch.setattr("bus.queue.asyncio.sleep", AsyncMock())
    bus = MessageBus()
    callback = AsyncMock(
        side_effect=[RuntimeError("first"), RuntimeError("second"), None]
    )
    bus.subscribe_outbound("chat", callback)
    message = OutboundMessage("chat", "one", "payload")
    await bus._dispatch_message(message)
    assert callback.await_count == 3
    assert (
        callback.await_args_list[-1].args[0].content == "（消息发送失败，请稍后重试）"
    )


@pytest.mark.asyncio
async def test_pending_outbound_tracks_queue_and_dispatch_until_completion():
    bus = MessageBus()
    entered = asyncio.Event()
    release = asyncio.Event()

    async def callback(message):
        entered.set()
        await release.wait()

    bus.subscribe_outbound("chat", callback)
    message = OutboundMessage(
        "chat", "one", "payload", metadata={"external_message_id": "origin-1"}
    )
    await bus.publish_outbound(message)
    assert bus.has_pending_outbound("chat", "one", "origin-1")
    assert not bus.has_pending_outbound("chat", "one", "origin-2")
    dispatcher = asyncio.create_task(bus.dispatch_outbound())
    try:
        await asyncio.wait_for(entered.wait(), 1)
        assert bus.has_pending_outbound("chat", "one", "origin-1")
        release.set()
        await asyncio.wait_for(bus.drain_outbound(), 1)
        assert not bus.has_pending_outbound("chat", "one", "origin-1")
    finally:
        bus.stop()
        dispatcher.cancel()
        with suppress(asyncio.CancelledError):
            await dispatcher
