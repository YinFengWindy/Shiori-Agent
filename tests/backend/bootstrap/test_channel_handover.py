import asyncio
import logging
from unittest.mock import AsyncMock

import pytest

from agent.tools.message_push import MessagePushTool
from bootstrap.channel_host import ChannelHost, ChannelHandoverError
from bus.queue import MessageBus
from bus.events import OutboundMessage
from infra.channels.contract import ChannelContext
from infra.channels.intake import ChannelIntake


class Connection:
    def __init__(
        self, label, events, *, fail_start=False, fail_stop=False, fail_resume=False
    ):
        self.name = "chat"
        self.label = label
        self.events = events
        self.fail_start = fail_start
        self.fail_stop = fail_stop
        self.fail_resume = fail_resume
        self.ctx = None
        self.intake = True

    def pause_intake(self):
        self.intake = False

    def resume_intake(self):
        self.intake = True
        if self.fail_resume:
            raise RuntimeError("resume failed")

    async def start(self, ctx):
        self.ctx = ctx
        self.intake = not ctx.intake_paused
        self.events.append(f"start:{self.label}")
        ctx.bus.subscribe_outbound(self.name, self.receive)
        ctx.push_tool.register_channel(self.name, text=self.send)
        if self.fail_start:
            raise RuntimeError("offline")

    async def stop(self):
        self.intake = False
        self.events.append(f"stop:{self.label}")
        if self.fail_stop:
            raise RuntimeError("disconnect failed")
        if self.ctx is not None:
            self.ctx.bus.unsubscribe_outbound(self.name, self.receive)
            self.ctx.push_tool.unregister_channel(self.name, text=self.send)

    async def receive(self, msg):
        await self.send(msg.chat_id, msg.content)

    async def send(self, chat_id, content):
        self.events.append(f"send:{self.label}:{content}")


def hosts(events, *, fail_start=False, fail_stop=False):
    bus = MessageBus()
    push = MessagePushTool()
    push.set_transport_lock(bus.transport_lock)
    ctx = ChannelContext(
        intake_factory=ChannelIntake,
        bus=bus,
        push_tool=push,
        session_manager=None,
        event_bus=None,
        attachment_store=None,
        http_resources=None,
        interrupt_controller=None,
        bot_commands=[],
        log=logging.getLogger(__name__),
    )
    old = Connection("old", events, fail_stop=fail_stop)
    new = Connection("new", events, fail_start=fail_start)
    active = ChannelHost(lambda channel: ctx, transport_lock=bus.transport_lock)
    candidate = ChannelHost(lambda channel: ctx, transport_lock=bus.transport_lock)
    active.add(old, configuration="old")
    candidate.add(new, configuration="new")
    return active, candidate, bus, push


@pytest.mark.asyncio
async def test_start_failure_cleans_candidate_subscriptions_and_restores_old():
    events = []
    active, candidate, bus, _ = hosts(events, fail_start=True)
    await active.start_all()
    with pytest.raises(ChannelHandoverError) as caught:
        await active.handover_channels(candidate, commit=None)
    assert caught.value.degraded == []
    assert events == ["start:old", "stop:old", "start:new", "stop:new", "start:old"]
    assert len(bus._subscribers["chat"]) == 1
    await bus._dispatch_message(
        OutboundMessage(channel="chat", chat_id="one", content="queued")
    )
    assert events[-1] == "send:old:queued"


@pytest.mark.asyncio
async def test_failed_stop_reports_degraded_connection_without_duplicate_start():
    events = []
    active, candidate, bus, _ = hosts(events, fail_stop=True)
    await active.start_all()
    with pytest.raises(ChannelHandoverError) as caught:
        await active.handover_channels(candidate, commit=None)
    assert caught.value.to_details()["degraded"][0]["phase"] == "stop"
    assert events == ["start:old", "stop:old"]
    assert len(bus._subscribers["chat"]) == 1


@pytest.mark.asyncio
async def test_commit_failure_restores_connection_and_does_not_adopt_candidate():
    events = []
    active, candidate, _, _ = hosts(events)
    await active.start_all()
    original = active.channels[0]

    def fail_commit():
        raise OSError("disk full")

    with pytest.raises(OSError, match="disk full"):
        await active.handover_channels(candidate, commit=fail_commit)
    assert active.channels == [original]
    assert original.intake
    assert not candidate.channels[0].intake
    assert events[-2:] == ["stop:new", "start:old"]


@pytest.mark.asyncio
async def test_resume_failure_prevents_commit_and_restores_original_transport():
    events = []
    active, candidate, bus, _ = hosts(events)
    await active.start_all()
    original = active.channels[0]
    active.pause_intake()
    candidate.channels[0].fail_resume = True
    commits = []
    with pytest.raises(ChannelHandoverError) as caught:
        await active.handover_channels(
            candidate, commit=lambda: commits.append("committed")
        )
    assert caught.value.failure.phase == "resume"
    assert caught.value.degraded == []
    assert commits == []
    assert active.channels == [original]
    assert original.intake
    assert not candidate.channels[0].intake
    await bus._dispatch_message(
        OutboundMessage(channel="chat", chat_id="one", content="old-credentials")
    )
    assert events[-1] == "send:old:old-credentials"


@pytest.mark.asyncio
async def test_reused_channel_is_resumed_before_commit():
    events = []
    active, candidate, _, _ = hosts(events)
    candidate._channels = active.channels
    await active.start_all()
    active.pause_intake()
    intake_at_commit = []
    await active.handover_channels(
        candidate, commit=lambda: intake_at_commit.append(active.channels[0].intake)
    )
    assert intake_at_commit == [True]


@pytest.mark.asyncio
async def test_commit_failure_repauses_candidate_before_async_cleanup_can_flush_input():
    events = []
    active, candidate, _, _ = hosts(events)
    await active.start_all()
    new = candidate.channels[0]
    accepted = AsyncMock()
    intake = ChannelIntake(accepted, new.send)
    start, stop = new.start, new.stop

    async def start_with_pending_input(ctx):
        await start(ctx)
        intake.start(paused=ctx.intake_paused)
        from bus.events import InboundMessage

        await intake.submit(
            InboundMessage(
                channel="chat", sender="user", chat_id="one", content="pending"
            )
        )

    async def stop_with_async_cleanup():
        await asyncio.sleep(0)
        await intake.close()
        await stop()

    def fail_commit():
        raise OSError("disk full")

    new.start = start_with_pending_input
    new.stop = stop_with_async_cleanup
    new.pause_intake = intake.pause
    new.resume_intake = intake.resume
    with pytest.raises(OSError, match="disk full"):
        await active.handover_channels(candidate, commit=fail_commit)
    accepted.assert_not_awaited()
    assert any(
        event.startswith("send:new:") and "重新发送" in event for event in events
    )


@pytest.mark.asyncio
async def test_unchanged_connection_is_preserved_without_start_or_stop():
    events = []
    active, candidate, bus, _ = hosts(events)
    candidate._channels = active.channels
    await active.start_all()
    await active.handover_channels(candidate, commit=lambda: events.append("commit"))
    assert events == ["start:old", "commit"]
    assert len(bus._subscribers["chat"]) == 1


@pytest.mark.asyncio
async def test_restore_failure_is_reported_separately_from_candidate_failure():
    events = []
    active, candidate, _, _ = hosts(events, fail_start=True)
    await active.start_all()
    active.channels[0].fail_start = True
    with pytest.raises(ChannelHandoverError) as caught:
        await active.handover_channels(candidate, commit=None)
    assert caught.value.failure.phase == "start"
    assert caught.value.degraded[0].phase == "restore"


@pytest.mark.asyncio
async def test_handover_blocks_direct_sends_until_new_connection_is_ready():
    events = []
    active, candidate, bus, push = hosts(events)
    await active.start_all()
    started = asyncio.Event()
    release = asyncio.Event()
    new = candidate.channels[0]
    original_start = new.start

    async def blocked_start(ctx):
        await original_start(ctx)
        started.set()
        await release.wait()

    new.start = blocked_start
    handover = asyncio.create_task(active.handover(candidate))
    await started.wait()
    assert not new.intake
    send = asyncio.create_task(
        push.execute(channel="chat", chat_id="one", message="old-task")
    )
    await asyncio.sleep(0)
    assert not send.done()
    release.set()
    await handover
    assert new.intake
    await send
    assert events[-1] == "send:new:old-task"
    assert len(bus._subscribers["chat"]) == 1


@pytest.mark.asyncio
async def test_removed_channel_keeps_old_replies_until_retirement_signal():
    events = []
    active, candidate, bus, _ = hosts(events)
    candidate._channels = []
    await active.start_all()
    old = active.channels[0]
    drained = asyncio.Event()
    await active.handover(candidate, retire_after=drained.wait)
    assert not old.intake
    assert active.channels == []
    await bus._dispatch_message(
        OutboundMessage(channel="chat", chat_id="one", content="last-reply")
    )
    assert events[-1] == "send:old:last-reply"
    drained.set()
    await active._retirements.drain()
    assert events[-1] == "stop:old"
    assert "chat" not in bus._subscribers


@pytest.mark.asyncio
async def test_readding_removed_channel_replaces_retained_transport_once():
    events = []
    active, candidate, bus, _ = hosts(events)
    await active.start_all()
    drained = asyncio.Event()
    empty = ChannelHost(candidate._ctx_factory, transport_lock=bus.transport_lock)
    await active.handover(empty, retire_after=drained.wait)
    await active.handover(candidate)
    assert len(bus._subscribers["chat"]) == 1
    drained.set()
    await active._retirements.drain()
    await bus._dispatch_message(
        OutboundMessage(channel="chat", chat_id="one", content="reply")
    )
    assert events[-1] == "send:new:reply"
    assert events.count("stop:old") == 1
