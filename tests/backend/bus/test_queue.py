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
    bus = MessageBus(outbound_retry_delay_s=0)
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
    fail_on_retry,
):
    bus = MessageBus(outbound_retry_delay_s=0)
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


@pytest.mark.asyncio
async def test_retryable_delivery_still_sends_error_notice_after_second_failure():
    bus = MessageBus(outbound_retry_delay_s=0)
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


@pytest.mark.asyncio
@pytest.mark.parametrize(("configured", "expected"), [({}, 2.0), ({"delay": 0.5}, 0.5)])
async def test_retry_waits_configured_delay_once_without_holding_lock(
    monkeypatch, configured, expected
):
    bus = (
        MessageBus(outbound_retry_delay_s=configured["delay"])
        if configured
        else MessageBus()
    )
    events: list[object] = []
    real_sleep = asyncio.sleep

    async def record_sleep(delay):
        events.append(("sleep", delay, bus.transport_lock.locked()))
        await real_sleep(0)

    # Only _dispatch_message runs here, so no test code depends on the real sleep.
    monkeypatch.setattr("bus.queue.asyncio.sleep", record_sleep)

    async def flaky(message):
        events.append("attempt")
        if events == ["attempt"]:
            raise RuntimeError("first")

    bus.subscribe_outbound("chat", flaky)
    await bus._dispatch_message(OutboundMessage("chat", "one", "payload"))
    assert events == ["attempt", ("sleep", expected, False), "attempt"]


async def _dispatch_until_drained(bus: MessageBus, *messages: OutboundMessage):
    dispatcher = asyncio.create_task(bus.dispatch_outbound())
    try:
        for message in messages:
            await bus.publish_outbound(message)
        await asyncio.wait_for(bus.drain_outbound(), 2)
    finally:
        bus.stop()
        dispatcher.cancel()
        with suppress(asyncio.CancelledError):
            await dispatcher


@pytest.mark.asyncio
async def test_retry_backoff_does_not_block_other_channels():
    # The backoff is long enough that serial dispatch would deliver "slow" first.
    bus = MessageBus(outbound_retry_delay_s=0.3)
    delivered: list[str] = []
    flaky_attempts: list[str] = []

    async def flaky(message):
        flaky_attempts.append(message.content)
        if len(flaky_attempts) == 1:
            raise RuntimeError("first")
        delivered.append(message.content)

    async def steady(message):
        delivered.append(message.content)

    bus.subscribe_outbound("flaky", flaky)
    bus.subscribe_outbound("steady", steady)
    await _dispatch_until_drained(
        bus,
        OutboundMessage("flaky", "one", "slow"),
        OutboundMessage("steady", "two", "fast"),
    )
    assert flaky_attempts == ["slow", "slow"]
    assert delivered == ["fast", "slow"]


@pytest.mark.asyncio
async def test_retry_backoff_keeps_same_channel_order():
    bus = MessageBus(outbound_retry_delay_s=0.05)
    attempts: list[str] = []
    delivered: list[str] = []

    async def flaky(message):
        attempts.append(message.content)
        if attempts == ["first"]:
            raise RuntimeError("first")
        delivered.append(message.content)

    bus.subscribe_outbound("chat", flaky)
    await _dispatch_until_drained(
        bus,
        OutboundMessage("chat", "one", "first"),
        OutboundMessage("chat", "one", "second"),
    )
    assert attempts == ["first", "first", "second"]
    assert delivered == ["first", "second"]


@pytest.mark.asyncio
async def test_retry_uses_replacement_transport_after_handover_during_backoff():
    bus = MessageBus(outbound_retry_delay_s=0.05)
    failed = asyncio.Event()
    received: list[str] = []

    async def old(message):
        failed.set()
        raise RuntimeError("stale connection")

    async def new(message):
        received.append(message.content)

    bus.subscribe_outbound("chat", old)
    dispatcher = asyncio.create_task(bus.dispatch_outbound())
    try:
        await bus.publish_outbound(OutboundMessage("chat", "one", "payload"))
        await asyncio.wait_for(failed.wait(), 1)
        # The first attempt released the transport lock, so a handover can land
        # while the retry is backing off.
        async with bus.transport_lock:
            bus.unsubscribe_outbound("chat", old)
            bus.subscribe_outbound("chat", new)
        await asyncio.wait_for(bus.drain_outbound(), 2)
    finally:
        bus.stop()
        dispatcher.cancel()
        with suppress(asyncio.CancelledError):
            await dispatcher
    assert received == ["payload"]


@pytest.mark.asyncio
async def test_unexpected_lane_failure_stops_dispatcher_immediately(monkeypatch):
    bus = MessageBus()

    async def broken_dispatch(message):
        raise LookupError("dispatch bug")

    monkeypatch.setattr(bus, "_dispatch_message", broken_dispatch)
    dispatcher = asyncio.create_task(bus.dispatch_outbound())
    try:
        await bus.publish_outbound(OutboundMessage("chat", "one", "payload"))
        # No further message arrives on this channel, yet the bug must surface.
        with pytest.raises(LookupError, match="dispatch bug"):
            await asyncio.wait_for(dispatcher, 0.5)
    finally:
        bus.stop()
        dispatcher.cancel()
        with suppress(asyncio.CancelledError, LookupError):
            await dispatcher


def _blocking_callback(delivered: list[str], gate: asyncio.Event, entered=None):
    async def callback(message):
        if entered is not None:
            entered.set()
        await gate.wait()
        delivered.append(message.content)

    return callback


async def _cancel(bus: MessageBus, dispatcher: asyncio.Task) -> None:
    bus.stop()
    dispatcher.cancel()
    await asyncio.gather(dispatcher, return_exceptions=True)


async def _settle_loop(predicate) -> None:
    for _ in range(100):
        if predicate():
            return
        await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_outbound_size_counts_lane_backlog_and_cancel_returns_it_to_queue():
    bus = MessageBus()
    delivered: list[str] = []
    gate, entered = asyncio.Event(), asyncio.Event()
    bus.subscribe_outbound("chat", _blocking_callback(delivered, gate, entered))
    dispatcher = asyncio.create_task(bus.dispatch_outbound())
    await bus.publish_outbound(OutboundMessage("chat", "one", "in-flight"))
    await asyncio.wait_for(entered.wait(), 1)
    for content in ("second", "third"):
        await bus.publish_outbound(
            OutboundMessage(
                "chat", "one", content, metadata={"external_message_id": content}
            )
        )
    # Both follow-ups have left the queue and sit in the lane behind "in-flight".
    await _settle_loop(lambda: bus._outbound.qsize() == 0 and bus.outbound_size == 2)
    assert bus._outbound.qsize() == 0
    assert bus.outbound_size == 2

    await _cancel(bus, dispatcher)
    # The cancelled lane hands its backlog back instead of stranding it.
    assert bus.outbound_size == 2
    assert bus.has_pending_outbound("chat", "one", "third")
    gate.set()
    dispatcher = asyncio.create_task(bus.dispatch_outbound())
    try:
        await asyncio.wait_for(bus.drain_outbound(), 1)
    finally:
        await _cancel(bus, dispatcher)
    assert delivered == ["second", "third"]
    assert not bus.has_pending_outbound("chat", "one", "third")


@pytest.mark.asyncio
async def test_crashed_lane_raises_and_keeps_its_backlog_queued(monkeypatch):
    bus = MessageBus()
    gate, entered = asyncio.Event(), asyncio.Event()

    async def broken_dispatch(message):
        entered.set()
        await gate.wait()
        raise LookupError("dispatch bug")

    monkeypatch.setattr(bus, "_dispatch_message", broken_dispatch)
    dispatcher = asyncio.create_task(bus.dispatch_outbound())
    try:
        await bus.publish_outbound(OutboundMessage("chat", "one", "first"))
        await asyncio.wait_for(entered.wait(), 1)
        await bus.publish_outbound(
            OutboundMessage(
                "chat", "one", "second", metadata={"external_message_id": "2"}
            )
        )
        await asyncio.sleep(0)
        gate.set()
        with pytest.raises(LookupError, match="dispatch bug"):
            await asyncio.wait_for(dispatcher, 1)
    finally:
        await _cancel(bus, dispatcher)
    assert bus.outbound_size == 1
    assert bus.has_pending_outbound("chat", "one", "2")


@pytest.mark.asyncio
async def test_stop_finishes_routed_lanes_without_taking_new_messages():
    bus = MessageBus()
    delivered: list[str] = []
    gate_a, entered_a = asyncio.Event(), asyncio.Event()
    gate_b, entered_b = asyncio.Event(), asyncio.Event()
    bus.subscribe_outbound("a", _blocking_callback(delivered, gate_a, entered_a))
    bus.subscribe_outbound("b", _blocking_callback(delivered, gate_b, entered_b))
    dispatcher = asyncio.create_task(bus.dispatch_outbound())
    try:
        await bus.publish_outbound(OutboundMessage("a", "one", "a-routed"))
        await bus.publish_outbound(OutboundMessage("b", "one", "b-routed"))
        await asyncio.wait_for(entered_a.wait(), 1)
        # Lane b is routed and waits for the transport lock held by lane a.
        await _settle_loop(lambda: bus._outbound.qsize() == 0)
        await _settle_loop(lambda: False)  # The dispatcher is idle in its next get.
        bus.stop()
        gate_a.set()  # Lane a finishing wakes the dispatcher, which observes stop().
        await asyncio.wait_for(entered_b.wait(), 1)
        await _settle_loop(lambda: False)  # Let the dispatcher act on stop().
        await bus.publish_outbound(OutboundMessage("a", "one", "after-stop"))
        await _settle_loop(lambda: bus.outbound_size == 0)
        assert not dispatcher.done()
        gate_b.set()
        await asyncio.wait_for(dispatcher, 1)
    finally:
        await _cancel(bus, dispatcher)
    assert delivered == ["a-routed", "b-routed"]
    # The message published after stop() stays queued for the next dispatcher.
    assert bus.outbound_size == 1


@pytest.mark.asyncio
async def test_partial_handover_does_not_retry_through_unrelated_replacement(caplog):
    bus = MessageBus(outbound_retry_delay_s=0.05)
    steady = AsyncMock()
    replacement = AsyncMock()
    failed = asyncio.Event()

    async def broken(message):
        failed.set()
        raise RuntimeError("stale")

    bus.subscribe_outbound("chat", steady)
    bus.subscribe_outbound("chat", broken)
    delivery = asyncio.create_task(
        bus._dispatch_message(OutboundMessage("chat", "one", "payload"))
    )
    await asyncio.wait_for(failed.wait(), 1)
    async with bus.transport_lock:
        bus.unsubscribe_outbound("chat", broken)
        bus.subscribe_outbound("chat", replacement)
    await asyncio.wait_for(delivery, 1)
    assert steady.await_count == 1
    replacement.assert_not_awaited()
    assert "失败的连接已被移除" in caplog.text


@pytest.mark.asyncio
async def test_full_handover_during_backoff_retries_through_all_replacements():
    bus = MessageBus(outbound_retry_delay_s=0.05)
    succeeded = AsyncMock()
    replacements = [AsyncMock(), AsyncMock()]
    failed = asyncio.Event()

    async def broken(message):
        failed.set()
        raise RuntimeError("stale")

    bus.subscribe_outbound("chat", succeeded)
    bus.subscribe_outbound("chat", broken)
    message = OutboundMessage("chat", "one", "payload")
    delivery = asyncio.create_task(bus._dispatch_message(message))
    await asyncio.wait_for(failed.wait(), 1)
    async with bus.transport_lock:
        bus.unsubscribe_outbound("chat", succeeded)
        bus.unsubscribe_outbound("chat", broken)
        for callback in replacements:
            bus.subscribe_outbound("chat", callback)
    await asyncio.wait_for(delivery, 1)
    assert all(
        callback.await_args_list[0].args == (message,) for callback in replacements
    )


@pytest.mark.asyncio
async def test_retry_without_any_transport_logs_the_lost_message(caplog):
    bus = MessageBus(outbound_retry_delay_s=0.05)
    failed = asyncio.Event()

    async def broken(message):
        failed.set()
        raise RuntimeError("stale")

    bus.subscribe_outbound("chat", broken)
    delivery = asyncio.create_task(
        bus._dispatch_message(OutboundMessage("chat", "one", "payload"))
    )
    await asyncio.wait_for(failed.wait(), 1)
    async with bus.transport_lock:
        bus.unsubscribe_outbound("chat", broken)
    await asyncio.wait_for(delivery, 1)
    assert "重试时没有可用的连接" in caplog.text
