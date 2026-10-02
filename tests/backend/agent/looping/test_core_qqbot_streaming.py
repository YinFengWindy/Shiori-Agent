"""End-to-end QQBot live streaming: host stream gate, live preview, final reply.

Only the network is faked (an ``httpx.MockTransport`` standing in for the
official API); the channel, the host ``ChannelDirectory`` and the agent loop's
stream sink are the real ones.
"""

from __future__ import annotations

from infra.channels.intake import ChannelIntake
import asyncio
import json
import logging
import inspect
from collections.abc import Callable, Awaitable
from unittest.mock import MagicMock
import websockets
from contextlib import suppress
from datetime import datetime

import httpx
import pytest

from agent.looping.core import AgentLoop
from bus.event_bus import EventBus
from shiori_sdk.messages import InboundMessage, OutboundMessage
from shiori_sdk.channel_events import TurnCancelled, TurnStarted
from bus.queue import MessageBus
from core.common.channel_directory import ChannelDirectory
from shiori_sdk.channels import ChannelContext
import plugins.qqbot.backend.streaming as qqbot_streaming
from plugins.qqbot.backend.channel import QQBotChannel
from plugins.qqbot.testing.http import MESSAGE_PATH, STREAM_PATH, QQBotHttp

SESSION_KEY = "role:mira"
CHAT_ID = "c2c:app:user-1"


class _PushTool:
    def register_channel(self, name: str, **kwargs: object) -> None:
        return None

    def unregister_channel(self, name: str, **kwargs: object) -> None:
        return None


class _Hub:
    """Routes like the real hub: the reply runs on the bound role's session."""

    def __init__(self) -> None:
        self.deliveries: list[str] = []

    def is_sender_allowed(self, **kwargs: object) -> bool:
        return True

    def route_inbound(self, message: InboundMessage) -> InboundMessage:
        message.metadata.update(
            {"role_id": "mira", "session_key_override": SESSION_KEY}
        )
        return message

    def mark_delivery(self, message: OutboundMessage, **kwargs: object) -> None:
        self.deliveries.append(str(kwargs["delivery_status"]))


class _Gateway:
    """A platform-facing WebSocket fixture; real channel code consumes every frame."""

    def __init__(self):
        self.frames: asyncio.Queue[str] = asyncio.Queue()
        self.frames.put_nowait(
            json.dumps({"op": 10, "d": {"heartbeat_interval": 60000}})
        )
        self.frames.put_nowait(
            json.dumps({"op": 0, "t": "READY", "d": {"user": {"id": "bot"}}})
        )

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    def __aiter__(self):
        return self

    async def __anext__(self):
        return await self.frames.get()

    async def send(self, payload):
        pass

    def message(self, message_id: str, content: str):
        self.frames.put_nowait(
            json.dumps(
                {
                    "op": 0,
                    "t": "C2C_MESSAGE_CREATE",
                    "d": {
                        "id": message_id,
                        "author": {"user_openid": "user-1"},
                        "content": content,
                    },
                }
            )
        )


class _QQApi(QQBotHttp):
    """Adds a live gateway and scenario overrides to the shared HTTP fixture."""

    def __init__(self) -> None:
        super().__init__()
        self.gateway = _Gateway()
        self.override: (
            Callable[[httpx.Request], httpx.Response | Awaitable[httpx.Response]] | None
        ) = None

    async def dispatch(self, request: httpx.Request) -> httpx.Response:
        result = (self.override or self.handler)(request)
        return await result if inspect.isawaitable(result) else result


async def _started_channel(api: _QQApi, monkeypatch: pytest.MonkeyPatch):
    """Start the public transport against fake external HTTP and WebSocket endpoints."""
    original_client = httpx.AsyncClient

    def client(*args, **kwargs):
        return original_client(
            *args, transport=httpx.MockTransport(api.dispatch), **kwargs
        )

    monkeypatch.setattr(httpx, "AsyncClient", client)
    monkeypatch.setattr(websockets, "connect", lambda _url: api.gateway)
    channel = QQBotChannel("app", "secret")
    event_bus = EventBus()
    hub = _Hub()
    bus = MessageBus()
    await channel.start(
        ChannelContext(
            intake_factory=ChannelIntake,
            bus=bus,
            session_manager=MagicMock(),
            event_bus=event_bus,
            push_tool=_PushTool(),
            attachment_store=MagicMock(),
            http_resources=MagicMock(),
            interrupt_controller=None,
            bot_commands=[],
            log=logging.getLogger("test.qqbot"),
            channel_hub=hub,
        )
    )
    await channel.wait_ready()
    api.gateway.message("msg-1", "天气如何")
    inbound = await asyncio.wait_for(bus.consume_inbound(), 1)
    assert isinstance(inbound, InboundMessage)
    await event_bus.observe(
        TurnStarted(
            session_key=SESSION_KEY,
            channel="qqbot",
            chat_id=CHAT_ID,
            content=inbound.content,
            timestamp=datetime.now(),
            external_message_id="msg-1",
        )
    )
    return channel, event_bus, hub, inbound, bus


def _stream_sink(channel: QQBotChannel, event_bus: EventBus, inbound: InboundMessage):
    """Builds the agent loop's stream sink exactly as a turn would."""
    loop = object.__new__(AgentLoop)
    loop._event_bus = event_bus
    loop._active_turn_states = {}
    directory = ChannelDirectory()
    directory.bind({"qqbot": channel}.get)
    loop._channel_directory = directory
    return AgentLoop._build_stream_event_sink(loop, inbound)


def _final_reply(content: str) -> OutboundMessage:
    return OutboundMessage(
        channel="qqbot",
        chat_id=CHAT_ID,
        content=content,
        metadata={
            "role_id": "mira",
            "session_key_override": SESSION_KEY,
            "external_message_id": "msg-1",
        },
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["timeout", "recall", "fallback_timeout", "image"])
async def test_bus_dispatch_does_not_replay_uncertain_or_partial_qq_delivery(
    monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    monkeypatch.setattr(qqbot_streaming, "LIVE_STREAM_MIN_INTERVAL_S", 0)
    api = _QQApi()
    channel, event_bus, hub, inbound, bus = await _started_channel(api, monkeypatch)

    def handler(request: httpx.Request) -> httpx.Response:
        result = api.handler(request)
        if request.url.path == STREAM_PATH:
            if failure == "timeout":
                raise httpx.ReadTimeout("stream receipt lost", request=request)
            if failure == "fallback_timeout":
                return httpx.Response(400)
            if failure == "recall" and json.loads(request.content)["input_state"] == 10:
                return httpx.Response(400)
        if request.method == "DELETE":
            return httpx.Response(500)
        if request.url.path == MESSAGE_PATH and "markdown" in json.loads(
            request.content
        ):
            if failure == "fallback_timeout":
                raise httpx.ReadTimeout("plain receipt lost", request=request)
        if request.url.path.endswith("/files"):
            return httpx.Response(500)
        return result

    api.override = handler
    sink = _stream_sink(channel, event_bus, inbound)
    assert sink is not None
    try:
        await sink("半句")
        await channel._drain_live_tasks()
        reply = _final_reply("半句话。")
        if failure == "image":
            reply.media = ["https://example.invalid/image.png"]
        await bus._dispatch_message(reply)
        assert api.markdown_messages() == (
            ["半句话。"] if failure == "fallback_timeout" else []
        )
        assert hub.deliveries == ["failed"]
        assert channel._live_states == {}
        assert channel._live_tasks == set()
    finally:
        await channel.stop()


@pytest.mark.asyncio
async def test_delayed_old_final_preserves_both_turns_stream_ownership(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(qqbot_streaming, "LIVE_STREAM_MIN_INTERVAL_S", 0)
    api = _QQApi()
    channel, event_bus, hub, first, bus = await _started_channel(api, monkeypatch)

    def handler(request: httpx.Request) -> httpx.Response:
        result = api.handler(request)
        if request.url.path == STREAM_PATH:
            body = json.loads(request.content)
            return httpx.Response(200, json={"id": f"stream-{body['msg_id']}"})
        return result

    api.override = handler
    # A newer inbound can change the channel's latest anchor before the old
    # turn even emits its first delta. Event ownership must retain msg-1.
    api.gateway.message("msg-2", "第二问")
    second = await asyncio.wait_for(bus.consume_inbound(), 1)
    assert isinstance(second, InboundMessage)
    first_sink = _stream_sink(channel, event_bus, first)
    second_sink = _stream_sink(channel, event_bus, second)
    assert first_sink is not None and second_sink is not None
    dispatcher = asyncio.create_task(bus.dispatch_outbound())
    try:
        async with bus.transport_lock:
            await first_sink("第一轮预览")
            await channel._drain_live_tasks()
            await bus.publish_outbound(_final_reply("第一轮完整回复"))
            loop = object.__new__(AgentLoop)
            loop._event_bus = event_bus
            await loop._observe_turn_started(second, SESSION_KEY)
            await second_sink("第二轮预览")
            await channel._drain_live_tasks()
        await asyncio.wait_for(bus.drain_outbound(), 1)
        assert len(channel._live_states) == 1
        second_reply = _final_reply("第二轮完整回复")
        second_reply.metadata["external_message_id"] = "msg-2"
        await bus.publish_outbound(second_reply)
        await asyncio.wait_for(bus.drain_outbound(), 1)
        bodies = api.stream_bodies()
        assert [
            (
                body["msg_id"],
                body["index"],
                body["input_state"],
                body.get("stream_msg_id"),
            )
            for body in bodies
        ] == [
            ("msg-1", 0, 1, None),
            ("msg-2", 0, 1, None),
            ("msg-1", 1, 10, "stream-msg-1"),
            ("msg-2", 1, 10, "stream-msg-2"),
        ]
        assert api.markdown_messages() == []
        assert hub.deliveries == ["sent", "sent"]
        assert channel._live_states == {}
        assert channel._live_tasks == set()
    finally:
        bus.stop()
        dispatcher.cancel()
        with suppress(asyncio.CancelledError):
            await dispatcher
        await channel.stop()


@pytest.mark.asyncio
@pytest.mark.parametrize("final_queued", [False, True])
async def test_cancelled_turn_cleans_only_abandoned_preview(
    monkeypatch: pytest.MonkeyPatch, final_queued: bool
) -> None:
    monkeypatch.setattr(qqbot_streaming, "LIVE_STREAM_MIN_INTERVAL_S", 0)
    api = _QQApi()
    channel, event_bus, hub, inbound, bus = await _started_channel(api, monkeypatch)
    sink = _stream_sink(channel, event_bus, inbound)
    assert sink is not None
    dispatcher = asyncio.create_task(bus.dispatch_outbound())
    try:
        async with bus.transport_lock:
            await sink("取消前的预览")
            await channel._drain_live_tasks()
            if final_queued:
                await bus.publish_outbound(_final_reply("已经提交的完整回复"))
            await event_bus.observe(
                TurnCancelled(SESSION_KEY, "qqbot", CHAT_ID, "msg-1")
            )
            assert bool(channel._live_states) is final_queued
            if not final_queued:
                assert api.calls[-1][:2] == (
                    "DELETE",
                    "/v2/users/user-1/messages/stream-1",
                )
                assert channel._reply_buffers == {}
                assert channel._live_stop_events == {}
            await event_bus.observe(
                TurnStarted(
                    SESSION_KEY,
                    "qqbot",
                    CHAT_ID,
                    "新问题",
                    datetime.now(),
                    external_message_id="msg-2",
                )
            )
        await asyncio.wait_for(bus.drain_outbound(), 1)
        assert channel._live_states == {}
        assert api.markdown_messages() == []
        assert hub.deliveries == (["sent"] if final_queued else [])
    finally:
        bus.stop()
        dispatcher.cancel()
        with suppress(asyncio.CancelledError):
            await dispatcher
        await channel.stop()


@pytest.mark.asyncio
@pytest.mark.parametrize("cancel_terminal", [False, True])
@pytest.mark.parametrize("request_fails", [False, True])
async def test_bus_cancelled_delivery_with_failed_recall_never_replays(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    cancel_terminal: bool,
    request_fails: bool,
) -> None:
    monkeypatch.setattr(qqbot_streaming, "LIVE_STREAM_MIN_INTERVAL_S", 0)
    api = _QQApi()
    channel, event_bus, hub, inbound, bus = await _started_channel(api, monkeypatch)
    entered = asyncio.Event()
    release = asyncio.Event()

    async def handler(request: httpx.Request) -> httpx.Response:
        result = api.handler(request)
        if request.url.path == STREAM_PATH:
            terminal = json.loads(request.content)["input_state"] == 10
            if terminal == cancel_terminal:
                entered.set()
                await release.wait()
                if request_fails:
                    return httpx.Response(500)
        if request.method == "DELETE":
            return httpx.Response(500)
        return result

    api.override = handler
    sink = _stream_sink(channel, event_bus, inbound)
    assert sink is not None
    await sink("取消前的预览")
    if cancel_terminal:
        await channel._drain_live_tasks()
    dispatch = asyncio.create_task(bus._dispatch_message(_final_reply("完整回复")))
    try:
        await asyncio.wait_for(entered.wait(), 1)
        await asyncio.sleep(0)
        dispatch.cancel()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(dispatch, 3)
        assert api.markdown_messages() == []
        assert hub.deliveries == ["failed"]
        recall_attempted = cancel_terminal == request_fails
        assert sum(method == "DELETE" for method, _, _ in api.calls) == int(
            recall_attempted
        )
        if recall_attempted:
            assert "取消投递后撤回流式预览失败" in caplog.text
        if cancel_terminal and request_fails:
            assert "取消流式投递后等待发送回执失败" in caplog.text
        assert channel._live_states == {}
        assert channel._live_tasks == set()
    finally:
        release.set()
        await channel.stop()
