"""End-to-end QQBot live streaming: host stream gate, live preview, final reply.

Only the network is faked (an ``httpx.MockTransport`` standing in for the
official API); the channel, the host ``ChannelDirectory`` and the agent loop's
stream sink are the real ones.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from types import SimpleNamespace
from typing import Any, cast

import httpx
import pytest

from agent.looping.core import AgentLoop
from bus.event_bus import EventBus
from bus.events import InboundMessage, OutboundMessage
from bus.events_lifecycle import TurnStarted
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
        metadata={"role_id": "mira", "session_key_override": SESSION_KEY},
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
    await channel._on_response(_final_reply("第一段第二段"))
    await channel._drain_live_tasks()

    assert [(b["index"], b["input_state"]) for b in api.stream_bodies()] == [
        (0, 1),
        (1, 10),
    ]
    assert channel._live_tasks == set()
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
    assert len(api.stream_bodies()) == 2
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
