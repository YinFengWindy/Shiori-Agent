"""Offline fakes for the Feishu REST API, the long connection and the host."""

from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any, cast

import httpx
import pytest

from bus.event_bus import EventBus
from bus.events import InboundMessage, OutboundMessage
from infra.channels.base import AttachmentStore
from infra.channels.contract import ChannelContext
from plugins.feishu.backend.channel import FeishuChannel
from plugins.feishu.backend.ws import EventCallback

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
CHAT_ID = "oc_chat"
OPEN_ID = "ou_user"


@dataclass
class FakeFeishu:
    """Answers Feishu REST calls in memory and records every request."""

    calls: list[tuple[str, str, Any]] = field(default_factory=list)
    messages: dict[str, dict[str, Any]] = field(default_factory=dict)
    failures: dict[str, list[tuple[int, int]]] = field(default_factory=dict)
    gate: asyncio.Event | None = None
    counter: int = 0

    def fail(self, key: str, *errors: tuple[int, int]) -> None:
        """Queues ``(http_status, code)`` answers for requests matching ``key``."""
        self.failures.setdefault(key, []).extend(errors)

    async def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/tenant_access_token/internal"):
            return httpx.Response(
                200, json={"code": 0, "tenant_access_token": "t-1", "expire": 7200}
            )
        body: Any = None
        if request.headers.get("content-type", "").startswith("application/json"):
            body = json.loads(request.content or b"null")
        self.calls.append((request.method, path, body))
        key = _route_key(request.method, path)
        queued = self.failures.get(key)
        if queued:
            status, code = queued.pop(0)
            return httpx.Response(status, json={"code": code, "msg": "fake error"})
        if key == "download" and self.gate is not None:
            await self.gate.wait()
        return self._answer(key, path)

    def _answer(self, key: str, path: str) -> httpx.Response:
        self.counter += 1
        if key in {"send", "reply"}:
            data: dict[str, Any] = {"message_id": f"om_{self.counter}"}
        elif key == "get":
            data = {"items": [self.messages[path.rsplit("/", 1)[-1]]]}
        elif key == "download":
            return httpx.Response(
                200, content=PNG, headers={"content-type": "image/png"}
            )
        elif key == "upload_image":
            data = {"image_key": "img_1"}
        elif key == "upload_file":
            data = {"file_key": "file_1"}
        elif key == "create_card":
            data = {"card_id": f"card_{self.counter}"}
        elif key == "bot":
            return httpx.Response(200, json={"code": 0, "bot": {"app_name": "Shiori"}})
        else:
            data = {}
        return httpx.Response(200, json={"code": 0, "msg": "success", "data": data})

    def bodies(self, key: str) -> list[Any]:
        return [body for m, p, body in self.calls if _route_key(m, p) == key]

    def keys(self) -> list[str]:
        """Route keys of every call except the background bot-info lookup."""
        keys = [_route_key(method, path) for method, path, _body in self.calls]
        return [key for key in keys if key != "bot"]

    def sent_texts(self) -> list[str]:
        """Markdown of every static card or text message sent (not live cards)."""
        texts: list[str] = []
        for body in self.bodies("send") + self.bodies("reply"):
            content = json.loads(body["content"])
            if body["msg_type"] == "text":
                texts.append(content["text"])
            elif body["msg_type"] == "interactive" and "body" in content:
                texts.append(content["body"]["elements"][0]["content"])
        return texts


def _route_key(method: str, path: str) -> str:
    if path.endswith("/reply"):
        return "reply"
    if "/resources/" in path:
        return "download"
    if path == "/open-apis/im/v1/messages":
        return "send"
    if path.startswith("/open-apis/im/v1/messages/"):
        return "delete" if method == "DELETE" else "get"
    if path.endswith("/im/v1/images"):
        return "upload_image"
    if path.endswith("/im/v1/files"):
        return "upload_file"
    if path.endswith("/bot/v3/info"):
        return "bot"
    if path == "/open-apis/cardkit/v1/cards":
        return "create_card"
    if path.endswith("/content"):
        return "stream_text"
    if path.endswith("/settings"):
        return "card_settings"
    if path.startswith("/open-apis/cardkit/v1/cards/"):
        return "update_card"
    return path


class FakeConnection:
    """A long connection that never touches the network.

    ``emit`` delivers an event on the runner thread exactly like the SDK and
    reports how long the handler blocked that thread (the ack latency).
    """

    def __init__(self, on_event: EventCallback, *, fail_connect: int = 0) -> None:
        self.on_event = on_event
        self.fail_connect = fail_connect
        self.connected = False
        self.disconnects = 0
        self.loop: asyncio.AbstractEventLoop | None = None
        self.thread_name = ""

    async def connect(self) -> None:
        self.loop = asyncio.get_running_loop()
        self.thread_name = threading.current_thread().name
        if self.fail_connect:
            raise RuntimeError("fake connect failure")
        self.connected = True

    def is_connected(self) -> bool:
        return self.connected

    async def keepalive(self) -> None:
        await asyncio.sleep(3600)

    async def disconnect(self) -> None:
        self.connected = False
        self.disconnects += 1

    def drop(self) -> None:
        """Simulates the server closing the socket."""
        self.connected = False

    def emit(self, envelope: dict[str, Any]) -> float:
        loop = self.loop
        assert loop is not None
        done = threading.Event()
        elapsed: list[float] = []

        def deliver() -> None:
            started = time.perf_counter()
            try:
                self.on_event(envelope)
            finally:
                elapsed.append(time.perf_counter() - started)
                done.set()

        loop.call_soon_threadsafe(deliver)
        assert done.wait(5)
        return elapsed[0]


class ConnectionFactoryRecorder:
    def __init__(self, *, fail_first: int = 0) -> None:
        self.connections: list[FakeConnection] = []
        self._fail_first = fail_first

    def __call__(self, on_event: EventCallback) -> FakeConnection:
        failing = len(self.connections) < self._fail_first
        connection = FakeConnection(on_event, fail_connect=int(failing))
        self.connections.append(connection)
        return connection

    async def wait_connected(self) -> FakeConnection:
        for _ in range(500):
            if self.connections and self.connections[-1].connected:
                return self.connections[-1]
            await asyncio.sleep(0.01)
        raise AssertionError("fake long connection never connected")


class Bus:
    def __init__(self) -> None:
        self.inbound: list[InboundMessage] = []
        self.outbound: list[tuple[str, object]] = []

    async def publish_inbound(self, message: InboundMessage) -> None:
        self.inbound.append(message)

    def subscribe_outbound(self, channel: str, callback: object) -> None:
        self.outbound.append((channel, callback))

    def unsubscribe_outbound(self, channel: str, callback: object) -> None:
        self.outbound = [item for item in self.outbound if item != (channel, callback)]


class PushTool:
    def __init__(self) -> None:
        self.registered: dict[str, dict[str, object]] = {}
        self.removed: list[str] = []

    def register_channel(self, name: str, **kwargs: object) -> None:
        self.registered[name] = kwargs

    def unregister_channel(self, name: str, **kwargs: object) -> None:
        self.removed.append(name)


class Hub:
    """Routes like the real hub: bound chats land on the role session."""

    def __init__(self, *, allowed: bool = True) -> None:
        self.allowed = allowed
        self.deliveries: list[str] = []

    def is_sender_allowed(self, **kwargs: object) -> bool:
        return self.allowed

    def route_inbound(self, message: InboundMessage) -> InboundMessage:
        message.metadata.update(
            {"role_id": "mira", "session_key_override": "role:mira"}
        )
        return message

    def resolve_runtime_session_key(self, channel: str, chat_id: str) -> str:
        return "role:mira"

    def mark_delivery(self, message: OutboundMessage, **kwargs: object) -> None:
        self.deliveries.append(str(kwargs["delivery_status"]))


class Interrupts:
    def __init__(self) -> None:
        self.requests: list[dict[str, str]] = []

    def request_interrupt(self, **kwargs: str) -> SimpleNamespace:
        self.requests.append(kwargs)
        return SimpleNamespace(message="已停止当前回复。")


@dataclass
class Harness:
    channel: FeishuChannel
    api: FakeFeishu
    factory: ConnectionFactoryRecorder
    bus: Bus
    push_tool: PushTool
    hub: Hub
    event_bus: EventBus
    interrupts: Interrupts
    context: ChannelContext

    async def start(self) -> FakeConnection:
        await self.channel.start(self.context)
        return await self.factory.wait_connected()

    async def settle(self) -> None:
        """Waits for inbound processing and intake admission on the host loop."""
        for _ in range(200):
            await asyncio.sleep(0)
            if not self.channel._inbound_tasks:
                break
            await asyncio.gather(*self.channel._inbound_tasks, return_exceptions=True)
        await self.channel._intake.drain()


def build_harness(tmp_path: Any, *, allowed: bool = True, **channel_kwargs: Any):
    api = FakeFeishu()
    factory = ConnectionFactoryRecorder(fail_first=channel_kwargs.pop("fail_first", 0))
    channel = FeishuChannel(
        "cli_app",
        "secret",
        "https://open.feishu.cn",
        transport=httpx.MockTransport(api.handler),
        connection_factory=factory,
        **channel_kwargs,
    )
    bus, push_tool, hub = Bus(), PushTool(), Hub(allowed=allowed)
    event_bus, interrupts = EventBus(), Interrupts()
    context = ChannelContext(
        bus=cast(Any, bus),
        session_manager=cast(Any, SimpleNamespace()),
        event_bus=event_bus,
        push_tool=cast(Any, push_tool),
        attachment_store=AttachmentStore(tmp_path / "uploads"),
        http_resources=cast(Any, SimpleNamespace()),
        interrupt_controller=cast(Any, interrupts),
        bot_commands=[],
        log=logging.getLogger("test.feishu"),
        channel_hub=cast(Any, hub),
    )
    return Harness(
        channel, api, factory, bus, push_tool, hub, event_bus, interrupts, context
    )


def message_event(
    *,
    message_id: str = "om_in_1",
    event_id: str = "ev_1",
    message_type: str = "text",
    content: dict[str, Any] | None = None,
    chat_type: str = "p2p",
    parent_id: str = "",
) -> dict[str, Any]:
    return {
        "header": {"event_id": event_id, "event_type": "im.message.receive_v1"},
        "event": {
            "sender": {"sender_id": {"open_id": OPEN_ID}, "sender_type": "user"},
            "message": {
                "message_id": message_id,
                "chat_id": CHAT_ID,
                "chat_type": chat_type,
                "message_type": message_type,
                "content": json.dumps(content or {"text": "你好"}, ensure_ascii=False),
                "parent_id": parent_id,
            },
        },
    }


@pytest.fixture
async def make_harness(tmp_path: Any) -> AsyncIterator[Any]:
    """Builds harnesses (``allowed=``, ``fail_first=``) and
    stops every channel at teardown."""
    built: list[Harness] = []

    def make(**kwargs: Any) -> Harness:
        harness = build_harness(tmp_path, **kwargs)
        built.append(harness)
        return harness

    yield make
    for harness in built:
        await harness.channel.stop()


@pytest.fixture
async def harness(make_harness: Any) -> Harness:
    return make_harness()


@pytest.fixture
def make_event() -> Any:
    return message_event
