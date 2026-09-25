"""End-to-end QQBot live streaming: host stream gate, live preview, final reply.

Only the network is faked (an ``httpx.MockTransport`` standing in for the
official API); the channel, the host ``ChannelDirectory`` and the agent loop's
stream sink are the real ones.
"""

from __future__ import annotations

import asyncio
import json
import logging
from contextlib import suppress
from datetime import datetime
from types import SimpleNamespace
from typing import Any, cast

import httpx
import pytest

from agent.looping.core import AgentLoop
from bus.event_bus import EventBus
from bus.events import InboundMessage, OutboundMessage
from bus.events_lifecycle import TurnCancelled, TurnStarted
from bus.queue import MessageBus
from core.common.channel_directory import ChannelDirectory
from infra.channels.base import AttachmentStore
from infra.channels.contract import ChannelContext
import plugins.qqbot.backend.streaming as qqbot_streaming
from plugins.qqbot.backend.channel import QQBotChannel

SESSION_KEY = "role:mira"
CHAT_ID = "c2c:user-1"
STREAM_PATH = "/v2/users/user-1/stream_messages"
MESSAGE_PATH = "/v2/users/user-1/messages"


class _Bus:
    def __init__(self) -> None:
        self.inbound: list[InboundMessage] = []

    async def publish_inbound(self, message: InboundMessage) -> None:
        self.inbound.append(message)

    def subscribe_outbound(self, channel: str, callback: object) -> None:
        return None

    def unsubscribe_outbound(self, channel: str, callback: object) -> None:
        return None


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


class _QQApi:
    """Records official API calls; stream calls answer with a stream id."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, Any]]] = []
        self.fail_stream_from: int | None = None

    def handler(self, request: httpx.Request) -> httpx.Response:
        if request.url.path == "/app/getAppAccessToken":
            return httpx.Response(200, json={"access_token": "tok", "expires_in": 7200})
        body = json.loads(request.content) if request.content else {}
        self.calls.append((request.method, request.url.path, body))
        if request.url.path == STREAM_PATH:
            if (
                self.fail_stream_from is not None
                and len(self.stream_bodies()) > self.fail_stream_from
            ):
                return httpx.Response(400, json={"message": "stream expired"})
            return httpx.Response(200, json={"id": "stream-1"})
        return httpx.Response(200, json={})

    def stream_bodies(self) -> list[dict[str, Any]]:
        return [body for _m, path, body in self.calls if path == STREAM_PATH]

    def markdown_messages(self) -> list[str]:
        return [
            body["markdown"]["content"]
            for method, path, body in self.calls
            if method == "POST" and path == MESSAGE_PATH and "markdown" in body
        ]


async def _started_channel(
    api: _QQApi,
) -> tuple[QQBotChannel, EventBus, _Hub, InboundMessage]:
    channel = QQBotChannel("app", "secret")
    channel._client = httpx.AsyncClient(transport=httpx.MockTransport(api.handler))

    async def _no_gateway() -> None:
        return None

    channel._gateway_loop = _no_gateway
    event_bus = EventBus()
    hub = _Hub()
    bus = _Bus()
    await channel.start(
        ChannelContext(
            bus=cast(Any, bus),
            session_manager=cast(Any, SimpleNamespace()),
            event_bus=event_bus,
            push_tool=cast(Any, _PushTool()),
            attachment_store=AttachmentStore(),
            http_resources=cast(Any, SimpleNamespace()),
            interrupt_controller=None,
            bot_commands=[],
            log=logging.getLogger("test.qqbot"),
            channel_hub=cast(Any, hub),
        )
    )
    await channel._handle_c2c(
        {"id": "msg-1", "author": {"user_openid": "user-1"}, "content": "天气如何"}
    )
    await channel._intake.drain()
    [inbound] = bus.inbound
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
    return channel, event_bus, hub, inbound


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


def test_qqbot_opts_c2c_chats_into_stream_events_and_prompt_rules() -> None:
    channel = QQBotChannel("app", "secret")
    directory = ChannelDirectory()
    directory.bind({"qqbot": channel}.get)

    assert directory.supports_stream_events("qqbot", "c2c:user-1")
    assert directory.supports_stream_events("qqbot", "user-1")
    assert not directory.supports_stream_events("qqbot", "group:group-1")
    assert not directory.supports_stream_events("qqbot", "bogus:x")
    hint = directory.system_prompt_hint("qqbot", "c2c:user-1")
    assert hint.startswith("## 官方 QQBot 渠道规则（硬性）")
    assert "`channel=qqbot`" in hint
    assert "c2c:<user_openid>" in hint
    assert directory.default_chat_type("qqbot") == "unknown"


@pytest.mark.asyncio
async def test_qqbot_turn_streams_a_live_preview_then_finishes_it_in_place(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(qqbot_streaming, "LIVE_STREAM_MIN_INTERVAL_S", 0.01)
    api = _QQApi()
    channel, event_bus, hub, inbound = await _started_channel(api)
    sink = _stream_sink(channel, event_bus, inbound)
    assert sink is not None

    # Deltas arriving while a refresh is pending coalesce into one request.
    await sink("今天")
    await sink("晴，")
    await channel._drain_live_tasks()
    await sink("最高 25 度")
    await channel._drain_live_tasks()
    await channel._on_response(_final_reply("今天晴，最高 25 度。"))

    bodies = api.stream_bodies()
    assert [
        (b["index"], b["input_state"], b["content_raw"], b.get("stream_msg_id"))
        for b in bodies
    ] == [
        (0, 1, "今天晴，", None),
        (1, 1, "今天晴，最高 25 度", "stream-1"),
        (2, 10, "今天晴，最高 25 度。", "stream-1"),
    ]
    assert {(b["msg_id"], b["event_id"], b["msg_seq"]) for b in bodies} == {
        ("msg-1", "msg-1", bodies[0]["msg_seq"])
    }
    assert api.markdown_messages() == []
    assert hub.deliveries == ["sent"]
    await channel.stop()


@pytest.mark.asyncio
async def test_qqbot_final_reply_cancels_a_throttled_refresh(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(qqbot_streaming, "LIVE_STREAM_MIN_INTERVAL_S", 60.0)
    api = _QQApi()
    channel, event_bus, _hub, inbound = await _started_channel(api)
    sink = _stream_sink(channel, event_bus, inbound)
    assert sink is not None

    await sink("第一段")
    await channel._drain_live_tasks()
    await sink("第二段")  # waits for the 60 s interval
    await asyncio.sleep(0)  # let the refresh enter its throttled wait
    await asyncio.wait_for(channel._on_response(_final_reply("第一段第二段")), 1)
    await channel._drain_live_tasks()

    assert [(b["index"], b["input_state"]) for b in api.stream_bodies()] == [
        (0, 1),
        (1, 10),
    ]
    assert channel._live_tasks == set()
    await channel.stop()


@pytest.mark.asyncio
@pytest.mark.parametrize("blocked_index", [0, 1])
async def test_final_reply_waits_for_inflight_stream_id_and_index(
    monkeypatch: pytest.MonkeyPatch, blocked_index: int
) -> None:
    monkeypatch.setattr(qqbot_streaming, "LIVE_STREAM_MIN_INTERVAL_S", 0)
    api = _QQApi()
    channel, event_bus, hub, inbound = await _started_channel(api)
    entered = asyncio.Event()
    release = asyncio.Event()

    async def handler(request: httpx.Request) -> httpx.Response:
        result = api.handler(request)
        if request.url.path == STREAM_PATH:
            body = json.loads(request.content)
            if body["index"] == blocked_index and body["input_state"] == 1:
                entered.set()
                await release.wait()
        return result

    await channel._client.aclose()
    channel._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    sink = _stream_sink(channel, event_bus, inbound)
    assert sink is not None
    if blocked_index:
        await sink("第一段")
        await channel._drain_live_tasks()
    await sink("第二段")
    await asyncio.wait_for(entered.wait(), 1)
    final = asyncio.create_task(channel._on_response(_final_reply("完整回复")))
    try:
        await asyncio.sleep(0)
        assert not final.done()
        release.set()
        await asyncio.wait_for(final, 1)
        bodies = api.stream_bodies()
        assert [body["index"] for body in bodies] == list(range(blocked_index + 2))
        assert [body.get("stream_msg_id") for body in bodies] == [None] + [
            "stream-1"
        ] * (blocked_index + 1)
        assert bodies[-1]["input_state"] == 10
        assert bodies[-1]["content_raw"] == "完整回复"
        assert api.markdown_messages() == []
        assert hub.deliveries == ["sent"]
    finally:
        release.set()
        await final
        await channel.stop()


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["timeout", "server", "missing_id", "recall"])
async def test_uncertain_stream_or_failed_recall_never_resends_or_marks_sent(
    monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    monkeypatch.setattr(qqbot_streaming, "LIVE_STREAM_MIN_INTERVAL_S", 0)
    api = _QQApi()
    channel, event_bus, hub, inbound = await _started_channel(api)

    def handler(request: httpx.Request) -> httpx.Response:
        result = api.handler(request)
        if request.url.path == STREAM_PATH:
            if failure == "timeout":
                raise httpx.ReadTimeout("response lost", request=request)
            if failure == "server":
                return httpx.Response(500)
            if failure == "missing_id":
                return httpx.Response(200, json={})
            if json.loads(request.content)["input_state"] == 10:
                return httpx.Response(400)
        if request.method == "DELETE":
            return httpx.Response(500)
        return result

    await channel._client.aclose()
    channel._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    sink = _stream_sink(channel, event_bus, inbound)
    assert sink is not None
    try:
        await sink("半句")
        await channel._drain_live_tasks()
        with pytest.raises((httpx.HTTPError, RuntimeError)):
            await channel._on_response(_final_reply("半句话。"))
        assert api.markdown_messages() == []
        assert hub.deliveries == ["failed"]
        assert channel._live_states == {}
        assert channel._live_tasks == set()
    finally:
        await channel.stop()


@pytest.mark.asyncio
@pytest.mark.parametrize("cancel_terminal", [False, True])
async def test_cancelled_final_delivery_waits_for_receipt_and_never_marks_sent(
    monkeypatch: pytest.MonkeyPatch, cancel_terminal: bool
) -> None:
    monkeypatch.setattr(qqbot_streaming, "LIVE_STREAM_MIN_INTERVAL_S", 0)
    api = _QQApi()
    channel, event_bus, hub, inbound = await _started_channel(api)
    entered = asyncio.Event()
    release = asyncio.Event()

    async def handler(request: httpx.Request) -> httpx.Response:
        result = api.handler(request)
        if request.url.path == STREAM_PATH:
            terminal = json.loads(request.content)["input_state"] == 10
            if terminal == cancel_terminal:
                entered.set()
                await release.wait()
        return result

    await channel._client.aclose()
    channel._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    sink = _stream_sink(channel, event_bus, inbound)
    assert sink is not None
    await sink("半句")
    if cancel_terminal:
        await channel._drain_live_tasks()
    final = asyncio.create_task(channel._on_response(_final_reply("半句话。")))
    try:
        await asyncio.wait_for(entered.wait(), 1)
        await asyncio.sleep(0)
        final.cancel()
        await asyncio.sleep(0)
        assert not final.done()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await final
        assert hub.deliveries == ["failed"]
        assert api.markdown_messages() == []
        assert channel._live_tasks == set()
        assert channel._live_states == {}
        if not cancel_terminal:
            assert api.calls[-1][:2] == ("DELETE", "/v2/users/user-1/messages/stream-1")
    finally:
        release.set()
        await channel.stop()


@pytest.mark.asyncio
async def test_qqbot_withdraws_a_broken_preview_before_the_fallback_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(qqbot_streaming, "LIVE_STREAM_MIN_INTERVAL_S", 0.01)
    api = _QQApi()
    api.fail_stream_from = 1
    channel, event_bus, hub, inbound = await _started_channel(api)
    sink = _stream_sink(channel, event_bus, inbound)
    assert sink is not None

    await sink("半句")
    await channel._drain_live_tasks()
    await sink("话")  # rejected: the preview is disabled for this turn
    await channel._drain_live_tasks()
    await channel._on_response(_final_reply("半句话。"))

    assert [(method, path) for method, path, _body in api.calls][-2:] == [
        ("DELETE", "/v2/users/user-1/messages/stream-1"),
        ("POST", MESSAGE_PATH),
    ]
    assert len(api.stream_bodies()) == 3
    assert api.markdown_messages() == ["半句话。"]
    assert hub.deliveries == ["sent"]
    await channel.stop()


@pytest.mark.asyncio
async def test_qqbot_group_chats_do_not_get_stream_events() -> None:
    channel = QQBotChannel("app", "secret")
    group = InboundMessage(
        channel="qqbot", sender="u", chat_id="group:g1", content="hi"
    )

    assert _stream_sink(channel, EventBus(), group) is None


@pytest.mark.asyncio
async def test_rejected_first_preview_safely_falls_back_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(qqbot_streaming, "LIVE_STREAM_MIN_INTERVAL_S", 0)
    api = _QQApi()
    api.fail_stream_from = 0
    channel, event_bus, hub, inbound = await _started_channel(api)
    sink = _stream_sink(channel, event_bus, inbound)
    assert sink is not None
    try:
        await sink("半句")
        await channel._drain_live_tasks()
        await channel._on_response(_final_reply("半句话。"))
        assert len(api.stream_bodies()) == 1
        assert api.markdown_messages() == ["半句话。"]
        assert not any(method == "DELETE" for method, _, _ in api.calls)
        assert hub.deliveries == ["sent"]
    finally:
        await channel.stop()


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["timeout", "recall", "fallback_timeout", "image"])
async def test_bus_dispatch_does_not_replay_uncertain_or_partial_qq_delivery(
    monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    monkeypatch.setattr(qqbot_streaming, "LIVE_STREAM_MIN_INTERVAL_S", 0)
    api = _QQApi()
    channel, event_bus, hub, inbound = await _started_channel(api)

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

    await channel._client.aclose()
    channel._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    sink = _stream_sink(channel, event_bus, inbound)
    assert sink is not None
    bus = MessageBus()
    bus.subscribe_outbound("qqbot", channel._on_response)
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
    channel, event_bus, hub, first = await _started_channel(api)

    def handler(request: httpx.Request) -> httpx.Response:
        result = api.handler(request)
        if request.url.path == STREAM_PATH:
            body = json.loads(request.content)
            return httpx.Response(200, json={"id": f"stream-{body['msg_id']}"})
        return result

    await channel._client.aclose()
    channel._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    # A newer inbound can change the channel's latest anchor before the old
    # turn even emits its first delta. Event ownership must retain msg-1.
    channel._last_c2c_msg_id["user-1"] = "msg-2"
    second = InboundMessage(
        channel="qqbot",
        sender="user-1",
        chat_id=CHAT_ID,
        content="第二问",
        metadata={**first.metadata, "external_message_id": "msg-2"},
    )
    first_sink = _stream_sink(channel, event_bus, first)
    second_sink = _stream_sink(channel, event_bus, second)
    assert first_sink is not None and second_sink is not None
    bus = MessageBus()
    bus.subscribe_outbound("qqbot", channel._on_response)
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
    channel, event_bus, hub, inbound = await _started_channel(api)
    bus = MessageBus()
    channel._bus = bus
    bus.subscribe_outbound("qqbot", channel._on_response)
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
    channel, event_bus, hub, inbound = await _started_channel(api)
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

    await channel._client.aclose()
    channel._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    sink = _stream_sink(channel, event_bus, inbound)
    assert sink is not None
    bus = MessageBus()
    bus.subscribe_outbound("qqbot", channel._on_response)
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
